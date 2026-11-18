"""Unit tests for Stage 3 Quality Filtering and Fault Injection."""

from __future__ import annotations

from typing import Any

import numpy as np

from audio_token_pipeline.bench.fault_injection import (
    generate_synthetic_clean_speech,
    inject_dc_offset,
    inject_hard_clipping,
    inject_noise_at_snr,
    inject_silence_padding,
    run_fault_injection_evaluation,
)
from audio_token_pipeline.config import FilterConfig
from audio_token_pipeline.stages.filter import (
    check_and_correct_dc_offset,
    check_clipping_runs,
    check_silence_ratio,
    compute_spectral_fingerprint,
    estimate_wada_snr,
    evaluate_segment_item,
)


def test_filter_clipping_clean_and_clipped() -> None:
    clean = generate_synthetic_clean_speech(duration_s=2.5)
    passed_clean, frac_clean = check_clipping_runs(clean)
    assert passed_clean is True
    assert frac_clean < 0.001

    # Injected 5% clipping
    clipped = inject_hard_clipping(clean, target_clipped_pct=5.0)
    passed_clipped, frac_clipped = check_clipping_runs(clipped)
    assert passed_clipped is False
    assert frac_clipped >= 0.001


def test_filter_dc_offset_correction() -> None:
    clean = generate_synthetic_clean_speech(duration_s=2.5)
    shifted = inject_dc_offset(clean, offset=0.05)

    mean_val, corrected, flagged = check_and_correct_dc_offset(shifted, max_offset=0.01)
    assert flagged is True
    assert abs(mean_val) > 0.04
    # Corrected signal must have DC removed
    assert abs(float(np.mean(corrected))) < 1e-4


def test_filter_silence_threshold() -> None:
    clean = generate_synthetic_clean_speech(duration_s=2.5)
    passed_clean, ratio_clean = check_silence_ratio(clean, max_silence_ratio=0.40)
    assert passed_clean is True

    # 60% silence padding
    silent = inject_silence_padding(clean, target_silence_ratio=0.60)
    passed_silent, ratio_silent = check_silence_ratio(silent, max_silence_ratio=0.40)
    assert passed_silent is False
    assert ratio_silent > 0.40


def test_filter_snr_threshold() -> None:
    clean = generate_synthetic_clean_speech(duration_s=2.5)
    passed_clean, snr_clean = estimate_wada_snr(clean, min_snr_db=18.0)
    assert passed_clean is True
    assert snr_clean >= 18.0

    # 0 dB noise
    noisy = inject_noise_at_snr(clean, target_snr_db=0.0)
    passed_noisy, snr_noisy = estimate_wada_snr(noisy, min_snr_db=18.0)
    assert passed_noisy is False
    assert snr_noisy < 18.0


def test_filter_duplicate_detection() -> None:
    from audio_token_pipeline.stages.filter import LSHDeduplicator

    clean1 = generate_synthetic_clean_speech(duration_s=3.0)
    fp1 = compute_spectral_fingerprint(clean1)

    # 40 dB perturbed near-duplicate
    clean1_near = inject_noise_at_snr(clean1, target_snr_db=40.0)
    fp1_near = compute_spectral_fingerprint(clean1_near)
    sim = float(np.dot(fp1, fp1_near))
    assert sim >= 0.95

    # Time shift perturbations (50ms and 100ms)
    sr_test = 24000
    clean_50ms = clean1[int(0.050 * sr_test) :]
    clean_100ms = clean1[int(0.100 * sr_test) :]
    sim_50ms = float(np.dot(fp1, compute_spectral_fingerprint(clean_50ms)))
    sim_100ms = float(np.dot(fp1, compute_spectral_fingerprint(clean_100ms)))
    assert sim_50ms >= 0.95
    assert sim_100ms >= 0.95

    # LSHDeduplicator index query
    lsh = LSHDeduplicator(dim=128, num_tables=8, num_bits=12, threshold=0.95)
    added_orig, match_orig, _ = lsh.query_and_add("seg_orig", fp1)
    assert added_orig is True
    assert match_orig is None

    # Querying 50ms time shift should match original
    added_shift, match_shift, sim_match = lsh.query_and_add(
        "seg_shift", compute_spectral_fingerprint(clean_50ms)
    )
    assert added_shift is False
    assert match_shift == "seg_orig"
    assert sim_match >= 0.95

    # Completely different audio
    np.random.seed(999)
    diff_audio = np.random.normal(0, 0.4, len(clean1)).astype(np.float32)
    fp_diff = compute_spectral_fingerprint(diff_audio)
    sim_diff = float(np.dot(fp1, fp_diff))
    assert sim_diff < 0.60


def test_evaluate_segment_eval_vs_production(tmp_path: Any) -> None:
    import soundfile as sf

    test_wav = tmp_path / "test_clip.wav"
    clean = generate_synthetic_clean_speech(duration_s=3.0)
    sf.write(test_wav, clean, 24000)

    cfg = FilterConfig()
    item = {
        "segment_id": "test_seg_01",
        "filepath": str(test_wav),
        "start_ms": 0,
        "end_ms": 3000,
        "duration_s": 3.0,
        "speech_prob": 0.92,
    }

    # Production mode
    res_prod = evaluate_segment_item(item, cfg, eval_mode=False)
    assert res_prod.passed is True
    assert len(res_prod.reason_codes) == 0

    # Low speech probability in production mode
    item_low_speech = dict(item)
    item_low_speech["speech_prob"] = 0.45
    res_low = evaluate_segment_item(item_low_speech, cfg, eval_mode=False)
    assert res_low.passed is False
    assert "NOT_SPEECH" in res_low.reason_codes


def test_fault_injection_suite_runs() -> None:
    results = run_fault_injection_evaluation(num_samples=25)
    assert results["clean_speech_false_reject"]["status"] == "PASS"
    for sm in results["filter_metrics_summary"]:
        assert sm["status"] == "PASS"


def test_run_filter_pipeline(tmp_path: Any) -> None:
    import soundfile as sf

    from audio_token_pipeline.catalog import Catalog
    from audio_token_pipeline.config import AppConfig
    from audio_token_pipeline.stages.filter import run_filter

    db_path = tmp_path / "test_cat.duckdb"
    cat = Catalog(db_path)
    audio_path = tmp_path / "clip.wav"
    clean = generate_synthetic_clean_speech(3.0)
    sf.write(audio_path, clean, 24000)

    # Register source & segment
    with cat.connection() as con:
        con.execute(
            "INSERT INTO sources (source_id, filepath, dataset, split, duration_s, sample_rate, channels, status, sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "test_src_01",
                str(audio_path),
                "test",
                "split",
                3.0,
                24000,
                1,
                "INGESTED",
                "dummy_sha256",
            ],
        )
        con.execute(
            "INSERT INTO segments (segment_id, source_id, start_ms, end_ms, duration_s, speech_prob) VALUES (?, ?, ?, ?, ?, ?)",
            ["test_seg_01", "test_src_01", 0, 3000, 3.0, 0.95],
        )

    cfg = AppConfig(catalog_path=db_path)
    res_eval = run_filter(cfg, num_workers=1, eval_mode=True)
    assert res_eval["items_in"] == 1
    assert res_eval["items_passed"] == 1
    assert res_eval["rejection_rate_pct"] == 0.0

    res_prod = run_filter(cfg, num_workers=1, eval_mode=False)
    assert res_prod["items_in"] == 1
    assert res_prod["items_passed"] == 1


def test_filter_empty_segments_run(tmp_path: Any) -> None:
    from audio_token_pipeline.catalog import Catalog
    from audio_token_pipeline.config import AppConfig
    from audio_token_pipeline.stages.filter import run_filter

    db_path = tmp_path / "empty_cat.duckdb"
    Catalog(db_path)
    cfg = AppConfig(catalog_path=db_path)
    res = run_filter(cfg, num_workers=1)
    assert res["items_in"] == 0
    assert res["items_passed"] == 0


def test_filter_edge_cases_and_chunk_processing(tmp_path: Any) -> None:
    import numpy as np
    import soundfile as sf

    from audio_token_pipeline.config import FilterConfig
    from audio_token_pipeline.stages.filter import (
        evaluate_segment_item,
        process_filter_chunk,
    )

    fcfg = FilterConfig()
    clean_path = tmp_path / "clean_edge.wav"
    sf.write(clean_path, generate_synthetic_clean_speech(3.0), 24000)

    # 1. Bad length
    item_bad_len = {
        "segment_id": "seg_bad_len",
        "filepath": str(clean_path),
        "start_ms": 0,
        "end_ms": 500,
        "duration_s": 0.5,
        "speech_prob": 0.95,
    }
    res_bl_prod = evaluate_segment_item(item_bad_len, fcfg, eval_mode=False)
    assert not res_bl_prod.passed
    assert "BAD_LENGTH" in res_bl_prod.reason_codes

    res_bl_eval = evaluate_segment_item(item_bad_len, fcfg, eval_mode=True)
    assert not res_bl_eval.passed
    assert "BAD_LENGTH" in res_bl_eval.reason_codes

    # 2. Not speech
    item_bad_speech = {
        "segment_id": "seg_bad_speech",
        "filepath": str(clean_path),
        "start_ms": 0,
        "end_ms": 3000,
        "duration_s": 3.0,
        "speech_prob": 0.20,
    }
    res_bs_prod = evaluate_segment_item(item_bad_speech, fcfg, eval_mode=False)
    assert not res_bs_prod.passed
    assert "NOT_SPEECH" in res_bs_prod.reason_codes

    res_bs_eval = evaluate_segment_item(item_bad_speech, fcfg, eval_mode=True)
    assert not res_bs_eval.passed
    assert "NOT_SPEECH" in res_bs_eval.reason_codes

    # 3. Read error
    item_read_err = {
        "segment_id": "seg_err",
        "filepath": str(tmp_path / "does_not_exist.wav"),
        "start_ms": 0,
        "end_ms": 3000,
        "duration_s": 3.0,
        "speech_prob": 0.95,
    }
    res_err = evaluate_segment_item(item_read_err, fcfg, eval_mode=False)
    assert not res_err.passed
    assert "READ_ERROR" in res_err.reason_codes

    # 4. Stereo file and early exits in prod mode
    stereo_path = tmp_path / "stereo.wav"
    clean_stereo = np.column_stack(
        [generate_synthetic_clean_speech(3.0), generate_synthetic_clean_speech(3.0)]
    )
    sf.write(stereo_path, clean_stereo, 24000)

    item_stereo = {
        "segment_id": "seg_stereo",
        "filepath": str(stereo_path),
        "start_ms": 0,
        "end_ms": 3000,
        "duration_s": 3.0,
        "speech_prob": 0.95,
    }
    res_stereo = evaluate_segment_item(item_stereo, fcfg, eval_mode=False)
    assert res_stereo.passed

    # 5. Clipped early exit
    clipped_path = tmp_path / "clipped.wav"
    clipped_audio = np.clip(generate_synthetic_clean_speech(3.0) * 10.0, -0.999, 0.999)
    sf.write(clipped_path, clipped_audio, 24000)
    item_clipped = {
        "segment_id": "seg_clip",
        "filepath": str(clipped_path),
        "start_ms": 0,
        "end_ms": 3000,
        "duration_s": 3.0,
        "speech_prob": 0.95,
    }
    res_clip_prod = evaluate_segment_item(item_clipped, fcfg, eval_mode=False)
    assert not res_clip_prod.passed
    assert "CLIPPED" in res_clip_prod.reason_codes

    # 6. Silent early exit
    sil_path = tmp_path / "silent.wav"
    sf.write(sil_path, np.zeros(24000 * 3, dtype=np.float32), 24000)
    item_sil = {
        "segment_id": "seg_sil",
        "filepath": str(sil_path),
        "start_ms": 0,
        "end_ms": 3000,
        "duration_s": 3.0,
        "speech_prob": 0.95,
    }
    res_sil_prod = evaluate_segment_item(item_sil, fcfg, eval_mode=False)
    assert not res_sil_prod.passed
    assert "TOO_SILENT" in res_sil_prod.reason_codes

    # 7. Low SNR early exit
    noisy_path = tmp_path / "noisy.wav"
    noise = np.random.randn(24000 * 3).astype(np.float32) * 0.5
    sf.write(noisy_path, noise, 24000)
    item_noisy = {
        "segment_id": "seg_noise",
        "filepath": str(noisy_path),
        "start_ms": 0,
        "end_ms": 3000,
        "duration_s": 3.0,
        "speech_prob": 0.95,
    }
    res_noise_prod = evaluate_segment_item(item_noisy, fcfg, eval_mode=False)
    assert not res_noise_prod.passed
    assert "LOW_SNR" in res_noise_prod.reason_codes

    # 8. process_filter_chunk with duplicate detection
    chunk_items = [
        item_stereo,
        {**item_stereo, "segment_id": "seg_stereo_dup"},
    ]
    chunk_results = process_filter_chunk(chunk_items, fcfg, eval_mode=False)
    assert len(chunk_results) == 2
    assert chunk_results[0].passed
    assert not chunk_results[1].passed
    assert "DUPLICATE_EXACT" in chunk_results[1].reason_codes
