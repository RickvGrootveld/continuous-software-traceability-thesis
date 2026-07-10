# Continuous Software Traceability Thesis

This branch is the main branch of the replication package of Rick van Grootveld his thesis. This branch contains the information of the project (in this file), the metric retrieval files (in the metric retrieval files folder), the result generation files (which are in the analysis map), and the ethics scan (in the root of this branch). Furthermore, there is an helper function (enrichment_log_to_csv.py) that has been used to retrieve the metrics from the log file created during the scalability run. By providing the insights into the analysis document, transparency into the analysis method is provided.

When you have access to the results of the experiment, the results folder should be placed in the root of this branch.

# Goal
This is the replication package of the Master thesis with the title: Continuous Software Traceability: LLM-Based Knowledge Graph Enrichment for Supporting Agile Software Evolution Activities. 
This replication package is used to produce the results in the experiment and has the purpose to make the research transparent by providing insights into the approach. 

## Project overview
Other branches in this replication package contain
- simulation
    - This branch contains the simulation part of the study. The simulation ranch simulates the continuous stream of events into the knowledge graph. The enrichment constantly tries to enrich this knowledge graph. The results obtained from these simulations have been used in the survey.
- scalability
    - This branch contains the scalability test of this study. Compared to the simulation branch, this branch contains an extra message protocol between the enrichment service and the knowledge graph service to control the input of the knowledge graph and thus the enrichment.
- prompt engineering
    - This branch contains the prompt engineering that has been done to end up with the prompt that has been used in the document.

## abstract of the research:
Software traceability enables the tracking of relationships between software arti-
facts throughout the software development lifecycle and supports agile practices
such as change impact analysis and developer information retrieval. Although
agile environments benefit from software traceability, maintaining accurate and
semantically meaningful trace links in agile and continuously evolving software
projects remains challenging due to incomplete, outdated, and weakly defined
relationships [1]. Advances in knowledge graphs and large language models
(LLMs) provide an opportunity to automate and enrich software traceability by
closing the gap of those structural and semantical deficiencies. This thesis pro-
poses a conceptual schema and a framework for LLM-based knowledge graph en-
richment in continuous software traceability environments. Using the framework,
I evaluate the performance, perceived quality, and the usefulness of enrichment in
evolving environments. A comparison between GPT-5.1 and Qwen3.5 4B has been
made to get insights into the enrichment by using different types of LLMs. The re-
sults indicate that performance depends on the degree of a node, with the size of
the graph contributing to the model’s performance. The perceived quality of the
created edges indicate a relationship with the freedom given to the LLM. Lastly,
usefulness shows no effect for change impact analysis. However, participants
showed preference of enriched graphs over non-enriched graphs for developer
information retrieval, which suggests that LLMs can contribute to the semantic
aspect. Due to limitation, future research should focus on efficiently retrieving rel-
evant graph context to provide the LLM of more focused graph enrichment.

[1] Antoniol, Giulio, et al. "Recovering traceability links between code and documentation: a retrospective." IEEE Transactions on Software Engineering 51.3 (2025): 825-832.

## Contact information
If there are any questions, please reach out to me.

GitHub username: RickvGrootveld