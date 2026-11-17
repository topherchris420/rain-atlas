# Vendored Mem0 code (Apache-2.0)

The files in this directory are adapted from the Mem0 project
(https://github.com/mem0ai/mem0) at commit
f1791da86d469249c9b002f62644d58a1eb96a0, which is licensed under the
Apache License, Version 2.0:

* ``scoring.py`` -- from ``mem0/utils/scoring.py`` (BM25 sigmoid
  normalization and additive hybrid ranking).
* ``lemmatization.py`` -- from ``mem0/utils/lemmatization.py``
  (optional spaCy lemmatization for BM25 matching).

Adaptations are limited to import paths and the optional spaCy loader;
the scoring logic is preserved from the reference. The full Apache-2.0
license text is in ``LICENSE`` next to this file.

Copyright 2023-2026 Mem0 AI and contributors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use these files except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
