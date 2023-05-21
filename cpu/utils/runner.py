from llama_cpp import Llama
from typing import List, Dict
from transformers import AutoTokenizer
import logging

def init_model(path, n_threads=4, n_ctx=2048, use_mlock=True) -> Llama:
    model = Llama(path, n_threads=n_threads, use_mlock=use_mlock,
                  n_ctx=n_ctx, verbose=False)
    return model

def run(prompt, model, config: Dict[str, any], max_tokens=128, stop=List[str], name=None) -> str:
    print(f"Running text generation for prompt: {prompt}")

    if isinstance(model, Llama):
        output = model(prompt,
                       max_tokens=max_tokens,
                       stop=stop,
                       top_p=config['top_p'],
                       top_k=config['top_k'],
                       temperature=config['temp'],
                       repeat_penalty=config['repeat_penalty']
                       )
        generated_text = output['choices'][0]['text']
    else:
        print(f"!!! NO SUPPORT YET FOR GTP")

    print(f"Generated Output: {generated_text}")

    return generated_text
    
    
    
    
    
