# Six-PDF knowledge graph evaluation

25 October 2026 (IST). The six supplied Transit and Energy PDFs are synthetic AI-03 evaluation fixtures; their claims are not real-world findings.

## Ingestion and review

| Measure | Observed result |
| --- | ---: |
| PDF documents | 6 |
| Pages | 18 |
| Indexed passages | 34 |
| First upload queued to last job completed | 74.102 seconds |
| Qwen 3.5 4B fact proposals | 16 |
| Approved, page-cited factual relationships | 15 |
| Rejected false proposal | 1 |

The rejected proposal incorrectly treated the CityMove-2024 dataset as a project evaluated on itself. Validation now rejects same-name project/target links, and all suggestions still require human review. The 15 approved method, dataset, and creator statements each cite page 2 of one of the six PDFs.

## Themes and graph

Topic discovery initially merged the two collections because the PDFs share template text. A repeated filename collection hint now separates them into **Transit** and **Energy**, with three documents in each approved topic.

The local SQLite graph reports **22 nodes and 21 edges**: 14 entity nodes, 2 topic nodes, 6 document nodes, 15 factual links, and 6 document-to-topic links. The two projects named Atlas have different IDs and different three-edge neighborhoods:

| Atlas context | Method | Dataset | Creator |
| --- | --- | --- | --- |
| Transit | LSTM | CityMove-2024 | TransitWorks Research |
| Energy | Gradient Boosting | SunGrid-2024 | HelioTech Lab |

Graph Neural Network is a shared Method node connecting MetroFlow and GridPulse. UrbanAI Lab is a shared Organization node connecting MetroFlow and SolarPilot. The three-hop path MetroFlow → Graph Neural Network → GridPulse → HelioTech Lab cites D01, D06, and D08 page 2.

## Query router checks

| Question | Route | Result |
| --- | --- | --- |
| What are the main themes across these reports? | TOPIC | Energy and Transit, 3 documents each |
| Which method does MetroFlow use? | GRAPH | Graph Neural Network; D01 p. 2 |
| Which dataset was Atlas evaluated on? | GRAPH | Both Atlas candidates with separate D02 and D07 citations |
| Who created Atlas? | GRAPH | Both creators with separate D03 and D08 citations |
| How are MetroFlow and GridPulse connected? | GRAPH | Two-edge path through Graph Neural Network; D01 and D06 p. 2 |
| Which organization is connected to MetroFlow through Graph Neural Network and GridPulse? | GRAPH | Three-edge path to HelioTech Lab; D01, D06, D08 p. 2 |
| What are the limitations of GridPulse forecasts? | VECTOR | Feeder-topology caveat; D06 pp. 1 and 3 |
| MetroFlow ने कौन सी विधि उपयोग की? | GRAPH | Hindi answer with D01 p. 2 graph path |
| What was MetroFlow's exact F1 score? | VECTOR | Abstained; no score supplied |

## Scope and limits

- Qwen proposes entities and relationships, but a reviewer must approve them. For this run, the reviewer explicitly reused the same project ID across its method, evaluation, and governance PDFs. Automatic cross-document project identity resolution remains conservative; it must not merge the two Atlas projects by name.
- This run used the SQLite-derived local graph because Neo4j was unavailable on the machine. The Neo4j deployment path was not verified here.
- Topic separation used repeated **Transit** and **Energy** filename prefixes plus embeddings. Collections with unclear names may need manual topic review.
- Source passages are treated as untrusted data. The six PDFs' guidance text did not authorize changes to the app or review decisions.
