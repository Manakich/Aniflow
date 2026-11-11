# AI benchmark for Manga Recap Automation

Status: experiment plan, 2026-11-11. This document does not change the existing AniFlow pipeline.

## Goal

Choose the best available zero-additional-cost writer for Russian manhwa/manga recap scripts. The production target is a continuous, original Russian narration of 5,000–10,000 words. The first experiment is deliberately smaller so the candidates can be compared quickly and fairly.

## Candidates

| Candidate | Access path | Role in the experiment | Constraints |
|---|---|---|---|
| Alice AI — Expert | Manual browser session at alice.yandex.ru | Russian-language long-form writer and multimodal plot reader | Expert quota is 20 requests/day without the separate Alice Plus option; unlimited Expert requests are advertised with that option. Do not assume ordinary Yandex Plus includes it. |
| DeepSeek Chat | Manual browser session | Baseline for Russian narration; include images only if the user's current interface accepts the same image set | Treat as a manual candidate, not an automated production dependency. |
| NVIDIA Nemotron 3.5 Super VL:free | OpenRouter API | Automated multimodal candidate | Free endpoint; OpenRouter currently documents 50 requests/day and 20/minute for :free variants. Provider may log inputs for service security and model improvement. Do not send confidential or rights-sensitive source material without reviewing the provider terms. |

## Alice AI: access and usage checks

- The official Alice help currently says Expert mode is available on alice.yandex.ru; without the separate Alice Plus option it is limited to 20 requests/day, while Alice Plus removes that quota.
- Alice Plus is a paid add-on to a Yandex Plus multi-subscription, not included automatically in every Yandex Plus plan. Do not purchase it for this project; use only access already active on the account.
- Alice AI's current service terms say that, without Alice Plus, generated content is for personal, non-commercial use. With the paid Alice Plus option, generated text and images may be used for other purposes. Confirm the user's exact subscription state before using Alice-generated scripts in monetized videos.
- The terms also give Yandex a broad license over user prompts and uploaded materials and allow content to be used to improve services. Therefore the benchmark should use only a small, low-risk test set for which the user has the necessary rights; do not bulk-upload whole copyrighted chapters.
- No public, supported API for the Alice Expert chat was identified in this research. Keep Alice as a manual comparison candidate; do not reverse-engineer private endpoints or build a Playwright bot for it.

## Fair test protocol

1. Pick one short chapter or sequence that the user is entitled to process. Keep the exact same ordered panel files for each multimodal candidate.
2. Use 20–30 representative panels in reading order for the pilot. Do not cherry-pick different scenes for different models.
3. Give every candidate the same Russian system instructions and the same target length (pilot: 1,500–2,000 words). Use the same number of continuation turns where the interface requires output in parts.
4. Ask for a recap, not an image-by-image caption list. The script must work as spoken narration and must not invent events, relationships, motives, powers, or dialogue that are not supported by the material.
5. Save each raw response unedited. Rename outputs candidate_A.md, candidate_B.md, etc. before scoring so the evaluator can judge writing quality without being influenced by the model brand.
6. After the pilot, run the best two candidates on a larger batch and test the actual production target of 5,000–10,000 words.

If a candidate cannot accept the same panel images, do not compare its multimodal plot accuracy directly. It may still enter a separate writing-only test using the exact same verified plot outline.

## Scorecard (100 points)

| Criterion | Weight | What to check |
|---|---:|---|
| Plot accuracy | 30 | Correct events, sequence, characters, cause and effect |
| Completeness | 20 | Important scenes and turning points are not omitted |
| Hallucinations | 20 | No invented events, dialogue, character traits or explanations |
| Spoken Russian | 15 | Natural, clear, non-robotic narration; easy to read aloud |
| Continuity and pacing | 10 | Coherent transitions; no repetitive panel-by-panel phrasing |
| Brief compliance | 5 | Word count, language, point of view and formatting |

Score each criterion from 0 to its maximum. Keep notes with concrete examples, not just a subjective overall impression. A model with the highest prose score must not win if it invents plot details.

## What to record

For every run, record:

- candidate and model/mode shown by the service;
- date, interface, and whether the account had Alice Plus active;
- number of panels and exact panel range;
- prompt version;
- number of turns / continuations;
- approximate word count;
- elapsed time;
- any failed, truncated or refused generation;
- score and examples of factual errors.

## Production decision rule

No provider is selected based on a provider's advertised benchmark alone. Production selection requires:
- acceptable plot accuracy and hallucination score;
- strong spoken Russian;
- a repeatable output length;
- zero additional spend;
- a permitted way to use the generated text for the intended publishing/monetization model;
- a practical and supportable access method.

The first implementation will use an official API where one exists. Browser automation is reserved for Secret Voicer, where the user has already confirmed the service and workflow. Alice remains a manual benchmark until an official automation route and commercial-use permission are established.
