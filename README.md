# continuous-software-traceability-thesis

This branch is the main branch of the replication package of Rick van Grootveld his thesis. This branch contains the information of the project (in this file), the metric retrieval files (in the metric retrieval files folder), the result generation files (which are in the analysis map), and the ethics scan (in the root of this branch). Furthermore, there is an helper function (enrichment_log_to_csv.py) that has been used to retrieve the metrics from the log file created during the scalability run. By providing the insights into the analysis document, transparency into the analysis method is provided.

When you have access to the results of the experiment, the folder results should be place in the root of this branch.

# Goal
This is the replication package of the Master thesis with the title: Continuous Software Traceability: LLM-Based Knowledge Graph Enrichment for Supporting Agile Software Evolution Activities. 
This replication package has the purpose to make the research transparent by providing insights into the approach. 

## Project overview
Other branches in this replication package contain
- simulation
    - This branch contains the simulation part of the study. The simulation ranch simulates the continuous stream of events into the knowledge graph. The enrichment constantly tries to enrich this knowledge graph. The results obtained from these simulations have been used in the survey.
- scalability
    - This branch contains the scalability test of this study. Compared to the simulation branch, this branch contains an extra message protocol between the enrichment service and the knowledge graph service to control the input of the knowledge graph and thus the enrichment.
- prompt engineering
    - This branch contains the prompt engineering that has been done to end up with the prompt that has been used in the document.

## Contact information
If there are any questions, please reach out to me.

GitHub username: RickvGrootveld