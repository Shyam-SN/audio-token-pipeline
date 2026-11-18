# Third-Party Licenses & Attributions

This project incorporates components, algorithms, and models subject to open-source licenses:

## 1. Silero VAD (ONNX Model)
- **Source:** [snakers4/silero-vad](https://github.com/snakers4/silero-vad)
- **License:** MIT License
- **Copyright:** (c) 2020-present Silero Team
- **Description:** Pre-trained voice activity detection ONNX model (`audio_token_pipeline/data/silero_vad.onnx`) bundled for deterministic, offline speech boundary extraction.

```
MIT License
Copyright (c) 2020-present Silero Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the condition that the copyright notice and
this permission notice appear in all copies or substantial portions of the Software.
```

## 2. ITU-R BS.1770-4 & EBU R128 Loudness (PyLoudnorm)
- **Source:** [csteinmetz1/pyloudnorm](https://github.com/csteinmetz1/pyloudnorm)
- **License:** MIT License
- **Copyright:** (c) 2020 Christian Steinmetz
- **Description:** K-weighting biquad IIR filter coefficients, gating window integration, and 4x oversampled true peak calculations conforming to ITU-R BS.1770-4 and EBU R128 standards.

```
MIT License
Copyright (c) 2020 Christian Steinmetz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

## 3. Philips Audio Fingerprinting / Haitsma-Kalker
- **Source Reference:** J. Haitsma and T. Kalker, "A Highly Robust Audio Fingerprinting System," *International Symposium on Music Information Retrieval (ISMIR)*, 2002.
- **Description:** 2D modulation spectrum subband energy decomposition and temporal frequency trajectories used for time-shift invariant near-duplicate audio detection and random hyperplane LSH indexing.

## 4. WADA-SNR Algorithm
- **Source Reference:** C. Kim and R. M. Stern, "Robust Signal-to-Noise Ratio Estimation Based on Waveform Amplitude Distribution Analysis," *Interspeech*, 2008 / CMU Sphinx.
- **Description:** Statistical amplitude and frame-energy percentile analysis (90th percentile speech vs 10th percentile noise floor) calibrated with empirical syllabic crest factor offsets for non-intrusive SNR estimation.

## 5. OpenAI Whisper & English Text Normalizer
- **Source:** [openai/whisper](https://github.com/openai/whisper)
- **License:** MIT License
- **Copyright:** (c) 2022 OpenAI
- **Description:** `EnglishTextNormalizer` regular expressions, spelling standardization, and contraction expansion for standardized Word Error Rate (WER) computation.

```
MIT License
Copyright (c) 2022 OpenAI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```
