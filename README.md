# Continuous Software Traceability Thesis

This branch is the prompt engineering branch of the replication package of Rick van Grootveld his thesis. It contains the source code that has been used to produce the results of the prompt evolution document. The program can easily be ran by having Python and Docker installed. 

Note that in the main.py file, the main function can run both of the models. The Qwen model runs by default while the GPT model functionalities are currently comments. If you want to run the GPT model, comment the line of running the Qwen model and uncomment the GPT model in the main function. 

## Project overview
Other branches in this replication package contain
- main
    - This branch contains the data analysis files, the ethics scan, metrics generation files, and what the project is about.
- simulation
    - This branch contains the simulation part of the study. The simulation branch simulates the continuous stream of events into the knowledge graph. The enrichment constantly tries to enrich this knowledge graph. The results obtained from these simulations have been used in the survey.
- scalability
    - This branch contains the scalability test of this study. Compared to the simulation branch, this branch contains an extra message protocol between the enrichment service and the knowledge graph service to control the input of the knowledge graph and thus the enrichment.

## Run the program
To run the program and replicating the research:

The branch has been set to the settings of using the Qwen model.To use the GPT API, you should have a OpenAI API key to run the GPT model and you should change the global variables in the llm.py file in the enrichment folder to set it to GPT. If you don't have the API key, you can still build the Qwen model using the following steps.

### Run Qwen3.5 4B model
Run the container
```
docker compose up ollama -d
```
download the model (if not already downloaded)
```
docker compose exec ollama ollama pull qwen3.5:4b
```
run the project
```
docker compose run app
```

### Run GPT-5.1 model
After commenting the lines of calling Qwen, Ollama and volume in the docker-compose.yml file:
```
docker compose up -d
```

## Contact information
If there are any questions, please reach out to me.

GitHub username: RickvGrootveld