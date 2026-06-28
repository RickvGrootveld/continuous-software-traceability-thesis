# Running the results of the prompt engineering document
To replicate the results of the prompt engineering document, run the following commands.
Note that in the main.py file, the main function can run both of the models. The Qwen model runs by default while the GPT model is outcomment. 
If you want to run the GPT model, comment the line of running the Qwen model and uncomment the GPT model in the main function. 


## Run Qwen3.5 4B model:
Run the container
```
docker compose up ollama -d
```
download the model (only once)
```
docker compose exec ollama ollama pull qwen3.5:4b
```
run the project
```
docker compose run app
```

## Run GPT-5.1 model:
After commenting the lines of calling Qwen and ollama and volume in the docker compose file:
```
docker compose up -d
```