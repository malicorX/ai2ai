import requests
import json

HOST = 'localhost:5000'
URI = f'http://{HOST}/api/v1/generate'

from colorama import Fore

class FormatterAI:
    def __init__(self, name, description, color):
        self.name = name
        self.description = description
        self.color = color

    def act(self, name, response):
        # create this characters prompt, based on his template and current memory (==conversation)
        character_prompt = f"""
### FORMATTING TASK:
You are tasked with formatting the following response from {name} into a narrative format. The response can either be thought, said, or acted by {name}. Choose the most appropriate format.

### RESPONSE TO FORMAT:
{response}

### YOUR FORMATTED RESPONSE:
"""
        print (Fore.WHITE + "[ FORMATTER-1 ] character_prompt: " + character_prompt)       
        
        # reformat the created response (to have it fit better into the story telling character
        formatted_character_response = self.generate_response(character_prompt)
        print (Fore.WHITE + "[ FORMATTER-2 ] formatted_character_response: " + formatted_character_response)
        
        #print(self.color + self.conversation)
            
        return formatted_character_response



    def generate_response(self, character_response):
        __DEBUG__ = False

        top_p = 0.8

        request = {
            'prompt': character_response,
            'max_new_tokens': 150,
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
            print (Fore.WHITE + " === ___DEBUG___ = BEGIN ==============================================")
            print (Fore.WHITE + "name: " + self.name)
            print (Fore.WHITE + "prompt: " + character_response)
            print (Fore.WHITE + "request: " + json.dumps(request))
            print (Fore.WHITE + "response: " + json.dumps(response.json()))
            print (Fore.WHITE + " === ___DEBUG___ = END   ==============================================")

        if response.status_code == 200:
            result = response.json()['results'][0]['text']
            response_text = result.split("### YOUR FORMATTED RESPONSE:")[-1].strip()
            return response_text
        else:
            print(Fore.RED + "ERROR!!! " + str(response.status_code))
            return None



