import json
import socket

from hourly_routine import run_one_hour
from memory import state
from settings import HOST, PORT

def read_messages(sock):

    decoder = json.JSONDecoder()
    text = ""
    while True:
        chunk = sock.recv(65536)
        if not chunk:                  
            return
        text += chunk.decode("utf-8")
        while text.strip():
            text = text.lstrip()
            try:
                message, end = decoder.raw_decode(text)
            except json.JSONDecodeError:
                break                  
            yield message
            text = text[end:]

def run_competition():
    print(f"Connecting to the server at {HOST}:{PORT} ...")
    with socket.create_connection((HOST, PORT)) as sock:
        for message in read_messages(sock):
            if not isinstance(message, dict):
                continue
            reply = run_one_hour(message)
            sock.sendall((json.dumps(reply) + "\n").encode("utf-8"))
    print(f"Day finished. Total cost: ${state['total_cost']:.2f}")
