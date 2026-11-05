# Modèle et paramètres des requêtes

[English](METHOD.md)

La confirmation a utilisé Qwen3-Coder-30B-A3B-Instruct avec la quantification UD-Q4_K_XL, servi localement par le build llama.cpp `b10639/5e6a37cb1`. Le fichier GGUF de 17 665 334 432 octets a pour empreinte SHA-256 `2841aa314d916434860cfb8990347528dcdfe5c350dbcb9d1461dbee88ff2533`. La fenêtre de contexte comptait 32 768 jetons. Chaque requête était limitée à 12 288 jetons d’entrée après rendu complet. L’admission bornait chaque appel modèle à 120 secondes. Les délais plus courts imposés par un appelant natif restaient applicables. Les caches de clés et de valeurs de l’attention utilisaient tous deux `q8_0`.

Les quatre conditions B partageaient le même modèle et les mêmes réglages natifs pour le planificateur, le Coder et le Reflector, avec trois tentatives Coder au maximum. Les plafonds de sortie par requête étaient de 512, 1 024 et 512 jetons pour ces trois rôles. Le planificateur et le Coder des tâches A disposaient chacun de 512 jetons en sortie. L’extraction LE était limitée à 768 jetons et l’observateur ECC à 1 536. Les requêtes enregistrées fixaient explicitement la température à 0,2 pour les cinq rôles Coder et à zéro pour les rôles LE et ECC.

[Le profil modèle](MODEL-PROFILES.json) résume les enveloppes de requête vérifiées après clôture. Les 484 requêtes B ont toutes été rattachées à leur condition. Pour chaque rôle, les paramètres explicites concordaient entre les conditions. Le profil donne les effectifs et les paramètres d’échantillonnage et de format autorisés. Il exclut les prompts, les réponses modèles et les détails d’hôte.
