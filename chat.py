import os
import streamlit as st
import openai
from elasticsearch import Elasticsearch
import json
import re

openai_api = os.environ['openai_api']
cloud_id = os.environ['cloud_id']
cloud_user = os.environ['cloud_user']
cloud_pass = os.environ['cloud_pass']

q = ""

pattern = "metrics-*"

openai.api_key = openai_api
model = "gpt-3.5-turbo-0301"


def es_connect():
    global es
    es = Elasticsearch(cloud_id=cloud_id, basic_auth=(cloud_user, cloud_pass))


def es_indexes():
    
    #GET _cat/indices/metrics-*?h=index&format=json&s=creation.date.string:desc
    
    i = es.cat.indices(index=pattern,h="index",format="text",s="creation.date.string:desc")
    i = i.replace("\n",",")
    return i

def chat_gpt(prompt, model="gpt-3.5-turbo", max_tokens=1024, max_context_tokens=4000, safety_margin=5):

    # Truncate the prompt content to fit within the model's context length
    truncated_prompt = truncate_text(prompt, max_context_tokens - max_tokens - safety_margin)

    response = openai.ChatCompletion.create(model=model,
                                            messages=[{"role": "user", "content": "You are an Elasticsearch expert."}, {"role": "user", "content": truncated_prompt}])

    return response["choices"][0]["message"]["content"]


def truncate_text(text, max_tokens):
    tokens = text.split()
    if len(tokens) <= max_tokens:
        return text

    return ' '.join(tokens[:max_tokens])

def select_index(i, q):

    prompt = "find relevant elasticsearch index from given json list comma separated in round bracket("+ i +") to find "+ q +". Give me only the index name part of the answer no extra explaination in text."

    answer = chat_gpt(prompt)

    index = ""

    for x in i.split(","):
        if x in answer:
            index = x
            break


    return index;

def format_json(j_str):
    return str(j_str).replace("'","\"").replace("False","\"False\"").replace("True","\"True\"")

def get_mapping(index):

    m = es.indices.get_mapping(index=index)
    m = format_json(m)
    return m


def validateJSON(jsonData):
    try:
        json.loads(jsonData)
    except ValueError as err:
        return False
    return True

def extract_text_between_backticks(s):

    t = s.split("\n")
    
    t.pop()
    
    j = ""
    
    for x in t.copy():
        if "{" in x:
            break
        else:
            t.remove(x)
    
    for e in t.copy():
        j += e+"\n"
    
    j = j.strip() 
    return j


def build_query(m, q):

    prompt = "which field need to use in given elasticsearch index mapping in round bracket("+ m +") to find "+ q +". Just return valid elasticsearch query and no explaination."

    j = chat_gpt(prompt)

    if not validateJSON(j):
        j = extract_text_between_backticks(j)

    return j


def es_query(i, json_query):

    t = json.loads(json_query)

    t["source"] = ["host.name","system"]
    t["index"] = i

    resp = es.search(**t)
    resp = format_json(resp['hits']['hits'])    
    return resp
     

es_connect()

st.title("Elastic Observability + ChatGPT")

# Main chat form
with st.form("chat_form"):
    q = st.text_input("You: ")
    submit_button = st.form_submit_button("Send")

if submit_button:

    metrics_indexes = es_indexes()
    index           = select_index(metrics_indexes, q)
    
    if index == "":
        st.write("Unable to find relevant index.")
        st.stop()
    else:
        st.write("\nFound relevant index to fetch mapping: "+index+"\n")
    
    m = get_mapping(index)
    json_query = build_query(m, q)

    if json_query == "" or json_query == []:
        st.write("\n Not a valid JSON Query \n")

    st.write("\n JSON Query \n")
    st.json(json_query)

    r = es_query(pattern, json_query)
    st.write("Response from Elasticsearch:\n\n")
    
    st.json(r)

    r="";
