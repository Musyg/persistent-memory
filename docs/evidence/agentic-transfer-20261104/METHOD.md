# Model and request settings

[Français](METHOD.fr.md)

The confirmation used Qwen3-Coder-30B-A3B-Instruct with the UD-Q4_K_XL quantization, served locally by llama.cpp build `b10639/5e6a37cb1`. The 17,665,334,432-byte GGUF has SHA-256 `2841aa314d916434860cfb8990347528dcdfe5c350dbcb9d1461dbee88ff2533`. The context window was 32,768 tokens. The complete rendered input was capped at 12,288 tokens per request. Model admission gave each call a 120-second envelope. Any shorter limits imposed by a native caller remained in effect. The key and value attention caches both used `q8_0`.

All four B conditions used the same model and native planner, Coder and Reflector configuration, with at most three Coder attempts. Their output caps per request were 512, 1,024 and 512 tokens, respectively. The A planner and Coder each had a 512-token output cap. LE extraction had a 768-token cap, and the ECC observer had a 1,536-token cap. The recorded requests explicitly set temperature 0.2 in the five Coder roles and zero in the LE and ECC roles.

[The model profile](MODEL-PROFILES.json) summarizes the verified request envelopes after closure. The 484 B requests were all attributed to their assigned conditions. The explicit settings matched across conditions for each role. The profile includes counts and approved sampling and response-format parameters. It excludes prompts, model responses and host details.
