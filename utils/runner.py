from llama_cpp import Llama
from typing import List, Dict
from transformers import AutoTokenizer
import logging

def init_model(path, n_threads=4, n_ctx=2048, use_mlock=True) -> Llama:
    model = Llama(path, n_threads=n_threads, use_mlock=use_mlock,
                  n_ctx=n_ctx, verbose=False)
    return model

def run(prompt, model, config: Dict[str, any], max_tokens=128, stop=List[str], name=None) -> str:
    logging.info(f"Running text generation for prompt: {prompt}")

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
        tokenizer = AutoTokenizer.from_pretrained('mosaicml/mpt-7b-storywriter', use_fast=True)
        input_ids = tokenizer.encode(prompt, return_tensors="pt")
        logging.info(f"Input Prompt encoded: {input_ids}")
        
        gen_tokens = model.generate(input_ids,
                                     max_length=input_ids.shape[-1] + max_tokens,
                                     pad_token_id=tokenizer.eos_token_id,
                                     do_sample=True,
                                     top_p=config['top_p'],
                                     top_k=config['top_k'],
                                     temperature=config['temp'],
                                     num_return_sequences=1)
        generated_text = tokenizer.decode(gen_tokens[:, input_ids.shape[-1]:][0], skip_special_tokens=True)

    logging.info(f"Generated Output: {generated_text}")

    return generated_text