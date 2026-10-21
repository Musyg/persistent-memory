# Memory on/off: eight paired tasks / Avec et sans mémoire : huit tâches comparées

[English](#english) · [Français](#français) · [Recorded data / Données enregistrées](evidence/memory-on-off-20261020/comparison.json)

## English

On 20 October 2026, an isolated **Hermes fact-enrichment response path** was run
with and without its admissible persistent facts. Each pair used the same task,
model and request limits. All names, facts and tasks are synthetic.

| Outcome | With memory | Without memory |
| --- | ---: | ---: |
| Task completed | 8 | 4 |
| Task not completed | 0 | 3 |
| Undetermined | 0 | 1 |
| Planned tasks | 8 | 8 |

Across the eight pairs, there were **three confirmed gains, no confirmed losses,
four successful ties and one undetermined pair**. The exact net gain is unknown:
it can range from three to four tasks within these eight cases. This is a
descriptive missing-result bound, not a confidence interval or an estimate of
production performance.

The three gains concerned a local return procedure, a parcel-hold procedure,
and an updated labelling rule that also applied to a small local batch. Both
arms answered the two self-contained tasks correctly and appropriately declined
the two requests without admissible information. A cautious answer can still
fail a task that requires an available local instruction; appropriate abstention
and task completion were scored separately.

One control answer is **missing**, rather than scored as incorrect. It requested
two parallel searches; the frozen test harness stopped before the second search
could complete. No complete answer was returned and the arm was not rerun. The
production loop can handle multiple searches; this observation does not establish
a production memory failure.

### What was held constant

There was one generation per arm, with first-arm order balanced across the eight
pairs. The requested model was `gpt-4.1`; all 17 returned model identifiers were
`gpt-4.1-2025-04-14`. Temperature was 0.7, with a ceiling of 2,048 output tokens,
11,264 input tokens and 10,240 request bytes. The selected consumer path, request
and limits were kept constant while admissible isolated facts were present or
absent. Equal ceilings do not imply equal token use. Intent was forced and the
tool catalogue reduced; natural routing and the full production bootstrap were
not exercised.

Two LLM annotators separately graded masked items against the same task criteria
before arm reconciliation. They agreed on all 16 primary verdicts, including the
unknown item. There were no human annotations; statistical independence and
perfect masking are not established. Two secondary disagreements about whether
conditional generic advice was supported are preserved in the data. They do not
create additional hallucination claims or change the primary coverage failures.

There were **17 provider requests, 16 attempted arms, 15 complete answers and no
retries**. The reservation debit was **$0.68**, not a provider invoice. Billed cost
and token totals are unknown; annotation-agent costs are outside this accounting.

### Inspect and verify

The [JSON export](evidence/memory-on-off-20261020/comparison.json) contains all eight
requests, seeded facts and their revocation status, shared grading criteria,
15 original French answers plus one explicit `null`, both anonymized annotations,
paired outcomes, accounting and source commitments. The original answers and
annotations remain in French; the English description does not replace them
with translated model outputs.

On Linux, from a source checkout with Python 3.11+:

```sh
python3 examples/verify_memory_comparison.py
```

No installation, network access, provider key or model is needed. The verifier
pins the published export, checks answer hashes, reconciles the two annotations,
and recomputes arm totals, paired outcomes, missing-result bounds and request
accounting. Its arithmetic is adapted directly from the frozen experiment's
aggregation. It does not rejudge answer meaning. Source hashes commit to the
source artifacts; the private sources are not distributed and those hashes alone
do not prove their contents. The public checker verifies the export's integrity
and internal consistency, not the authenticity of a newly performed experiment.

This is **not an autonomous public replay of the private Hermes integration** or
a benchmark of the standalone public library. It is a small selected synthetic
cohort, with one stochastic generation per arm. It establishes no representative
quality, latency, cost or SOTA superiority. The earlier **12/12 functional tasks**
(eight completions and four expected abstentions after corrections) are a
separate milestone and are not added to this cohort. The deterministic
[core/cache demonstration](PORTFOLIO-DEMO.md#reproduce-the-comparison--reproduire-la-comparaison)
is also a different experiment.

## Français

Le 20 octobre 2026, un **parcours isolé de réponse factuelle Hermes** a été exécuté
avec puis sans ses faits persistants admissibles. Chaque paire a reçu la même
demande, le même modèle et les mêmes plafonds. Noms, faits et tâches sont fictifs.

| Résultat | Avec mémoire | Sans mémoire |
| --- | ---: | ---: |
| Tâche accomplie | 8 | 4 |
| Tâche non accomplie | 0 | 3 |
| Indéterminé | 0 | 1 |
| Tâches prévues | 8 | 8 |

La comparaison donne **trois gains confirmés, aucune perte confirmée, quatre
égalités réussies et une paire indéterminée**. L'écart net exact reste inconnu :
il se situe entre trois et quatre tâches sur ces huit cas. Cette borne décrit
l'effet du résultat manquant ; ce n'est ni un intervalle de confiance, ni une
estimation des performances en production.

Les trois gains portent sur une procédure locale de retour, une manipulation de
mise en attente d'un colis et une règle d'étiquetage actualisée valable aussi
pour un petit lot local. Les deux bras réussissent les deux demandes
autosuffisantes et s'abstiennent correctement face aux deux demandes sans
information admissible. Une réponse prudente peut cependant ne pas accomplir
une tâche qui nécessite une consigne locale disponible : prudence et complétion
ont été évaluées séparément.

Une réponse sans mémoire est **manquante**, et non notée incorrecte. Le modèle a
demandé deux recherches parallèles ; le banc figé s'est arrêté avant de traiter
la seconde. Aucune réponse complète n'a été remise et ce bras n'a pas été rejoué.
La boucle de production sait traiter plusieurs recherches ; cet incident ne
démontre pas une défaillance de sa mémoire.

### Conditions de la mesure

Chaque bras a été généré une seule fois, avec un ordre de passage équilibré sur
les huit paires. Le modèle demandé était `gpt-4.1` ; les 17 identifiants renvoyés
étaient `gpt-4.1-2025-04-14`. La température était de 0,7, avec des plafonds de
2 048 tokens de sortie, 11 264 tokens d'entrée et 10 240 octets par requête.
Le parcours sélectionné, la demande et les limites sont restés identiques ;
seule la présence des faits isolés admissibles variait. Des plafonds égaux ne
signifient pas une consommation identique. L'intention était imposée et le
catalogue d'outils réduit ; ni le routage naturel ni le démarrage complet de la
production n'ont été testés.

Deux juges IA ont annoté séparément les items masqués selon les mêmes critères
avant rapprochement des bras. Ils s'accordent sur les 16 verdicts primaires,
dont un indéterminé. Il n'y a aucune annotation humaine ; l'indépendance
statistique et un masquage parfait ne sont pas établis. Deux désaccords
secondaires sur le soutien de conseils génériques conditionnels restent visibles.
Ils ne justifient aucune accusation supplémentaire d'hallucination et ne
changent pas les échecs de couverture retenus.

L'exécution totalise **17 requêtes fournisseur, 16 bras tentés, 15 réponses
complètes et aucun nouvel essai**. Les **0,68 USD débités de réservation** ne sont
pas un coût facturé. Facture et total de tokens sont inconnus ; les coûts des
agents d'annotation ne sont pas inclus dans cette comptabilité.

### Consulter et vérifier

L'[export JSON](evidence/memory-on-off-20261020/comparison.json) contient les huit
demandes, les faits préparés et leur état de révocation, les critères communs,
les 15 réponses françaises originales et une réponse explicitement `null`, les
deux annotations anonymisées, les résultats par paire, la comptabilité et les
empreintes sources. Les réponses et annotations originales sont conservées en
français, sans traduction présentée comme une nouvelle sortie du modèle.

Sous Linux, depuis le dépôt et avec Python 3.11+ :

```sh
python3 examples/verify_memory_comparison.py
```

Aucune installation, connexion réseau, clé fournisseur ou modèle n'est requis.
Le vérificateur contrôle l'empreinte de l'export et des réponses, rapproche les
deux annotations, puis recalcule les totaux, les résultats par paire, les bornes
du résultat manquant et le nombre de requêtes. Ce calcul reprend celui de
l'agrégation figée ; il ne réévalue pas le sens des réponses. Les empreintes
sources engagent les artefacts d'origine sans en distribuer le contenu privé.
Elles ne suffisent pas à prouver ce contenu. Le script contrôle l'intégrité et
la cohérence interne de l'export, sans authentifier une nouvelle expérience.

Ce paquet **ne permet pas de rejouer de manière autonome l'intégration privée
Hermes** et ne constitue pas un benchmark du noyau public seul. Huit cas
synthétiques choisis et une génération stochastique par bras ne permettent aucune
conclusion représentative de qualité, latence, coût ou supériorité SOTA. Le jalon
antérieur de **12/12 tâches fonctionnelles** (huit réalisations et quatre
abstentions attendues après corrections) reste distinct et n'est pas additionné
à ces huit cas. La [démonstration déterministe noyau/cache](PORTFOLIO-DEMO.md#reproduce-the-comparison--reproduire-la-comparaison)
porte, elle aussi, sur une autre question.
