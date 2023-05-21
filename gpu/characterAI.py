import requests
import json

from gpu.formatterAI import FormatterAI

HOST = 'localhost:5000'
URI = f'http://{HOST}/api/v1/generate'

from colorama import Fore

class CharacterAI:
    def __init__(self, name, description, conversation, color):
        self.name = name
        self.description = description
        self.color = color
        self.conversation = conversation

    def act(self, i):
        # init a formatterAI that will later on format this characters response better
        formatter = FormatterAI("Formatter", "an AI designed to format responses.", Fore.LIGHTBLACK_EX)

        # create this characters prompt, based on his template and current memory (==conversation)
        character_prompt = f"""
### YOUR CHARACTER:
You are {self.name}, {self.description}.

### CONVERSATION SO FAR:{self.conversation}

### YOUR RESPONSE:
"""
        print (Fore.WHITE + "[ " + str(i) +  "-1 ] character_prompt: " + character_prompt)
        
        # create a response from the current character, regarding the just built prompt
        character_response = self.generate_response(character_prompt)
        print (Fore.WHITE + "[ " + str(i) +  "-2 ] character_response: " + character_response)
        
        if character_response:
            # reformat the created response (to have it fit better into the story telling character
            formatter_prompt = formatter.create_prompt(self.name, character_response)
            formatted_character_response = formatter.generate_response(formatter_prompt, 0.8)
            self.conversation += formatted_character_response + "\n"
            print (Fore.WHITE + "[ " + str(i) +  "-3 ] self.conversation reformatted: " + self.conversation)
            
            #print(self.color + self.conversation)
            
        else:
            print("Error generating " + self.name + "'s response. Exiting.")
            return
    



    def generate_response(self, prompt):
        __DEBUG__ = False

        top_p = 0.8

        request = {
            'prompt': prompt,
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
            print (Fore.WHITE + "prompt: " + prompt)
            print (Fore.WHITE + "request: " + json.dumps(request))
            print (Fore.WHITE + "response: " + json.dumps(response.json()))
            print (Fore.WHITE + " === ___DEBUG___ = END   ==============================================")

        if response.status_code == 200:
            result = response.json()['results'][0]['text']
            response_text = result.split("### YOUR RESPONSE:")[-1].strip()
            return response_text
        else:
            print(Fore.RED + "ERROR!!! " + str(response.status_code))
            return None

