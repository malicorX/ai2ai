import requests
import json

HOST = 'localhost:5000'
URI = f'http://{HOST}/api/v1/generate'

from colorama import Fore

class NarratorAI():
    def __init__(self, name, description, color):
        self.name = name
        self.description = description
        self.color = color
           
    def create_prompt(self, conversation, top_p):
        __DEBUG__ = False

        prompt = f"""
    ### FORMATTING TASK:
    You are tasked with telling the story environment and setting, where people are and what they plan to do.

    ### CONVERSATION SO FAR:
    {conversation}

    ### CONTINUE HERE:
    """

        if (__DEBUG__):
            print (" === ___DEBUG___ = BEGIN ==============================================")
            print ("name: " + self.name)
            print ("conversation: " + conversation)  # change this line
            print ("prompt: " + prompt)
            print (" === ___DEBUG___ = END   ==============================================")

        return prompt

    def generate_response(self, prompt, top_p):
        __DEBUG__ = False
    
        request = {
            'prompt': prompt,
            'max_new_tokens': 300,
            'do_sample': True,
            'temperature': 1.3,
            'top_p': top_p,
            'typical_p': 1,
            'repetition_penalty': 1.18,
            'top_k': 40,
            'min_length': 0,
            'no_repeat_ngram_size': 0,
            'num_beams': 1,
            'penalty_alpha': 0,
            'length_penalty': 1,
            'early_stopping': False,
            'seed': -1,
            'add_bos_token': True,
            'truncation_length': 2048,
            'ban_eos_token': False,
            'skip_special_tokens': True,
            'stopping_strings': []
        }

        response = requests.post(URI, json=request)

        if (__DEBUG__):
            print (" === ___DEBUG___ = BEGIN ==============================================")
            print ("name: " + self.name)
            print ("prompt: " + prompt)
            print ("request: " + json.dumps(request))
            print ("response: " + json.dumps(response.json()))
            print (" === ___DEBUG___ = END   ==============================================")


        if response.status_code == 200:
            result = response.json()['results'][0]['text']
            print(Fore.RED + "NO ERROR!!! response.json(): " + json.dumps(response.json()) + " | " + str(response.status_code))
            response_text = result.split("### YOUR RESPONSE:")[-1].strip()
            print(Fore.RED + "NO ERROR!!! response_text: " + response_text + " | " + str(response.status_code))
            return response_text
        else:
            print(Fore.RED + "ERROR!!! " + str(response.status_code))
            return None
