import os
import sys
import json
import argparse

from colorama import Fore, Style, init

from gpu.characterAI import CharacterAI
from gpu.narratorAI import NarratorAI

init(autoreset=True)  # Automatically reset color back to default after print


def parse_args():
    parser = argparse.ArgumentParser(description='Process some model path.')
    parser.add_argument('--model_name', type=str, help='name of the model')
    return parser.parse_args()


def main():
    args = parse_args()
    model_name = args.model_name
    
    print("MODEL_NAME: " + model_name)

    narrator = NarratorAI("Narrator", "an AI designed to tell the story setting and environment", Fore.GREEN)
    
    peter = CharacterAI("Peter", "a tennis professional from New York, 29 years old.", """
A calm night in New York City.
""", Fore.BLUE)
    mary = CharacterAI("Mary", "an environmentalist, passionate about climate change.", """
A calm night in New York City.
""", Fore.RED)


#    characters = [peter, mary]
    characters = [peter]
    
    i = 0
    while True:
        i += 1

        for character in characters:
            # --- EXPLANATION -------------------------------------------------
            # each character gets the following input (==longterm memory), which is used to generate his answer:
            # 
            # - conversation: this contains the complete conversation from everybody so far                                 TODO: take out all "thinks" here
            # - TODO: add stuff like google search / wolfram alpha and so on
            #
            # --- EXPLANATION -------------------------------------------------
            
            character.act(i)
            

#        print(Fore.LIGHTBLACK_EX + conversation)

        if i == 1:
            break

if __name__ == '__main__':
    main()