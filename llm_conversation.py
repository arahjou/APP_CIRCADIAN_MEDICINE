# gemma3:12b
# qwen3:8b
# llama3.2
# phi4:14b
def llm_conversation(abstract, content):
    import ollama
    try:
        response = ollama.chat(
            model="phi4:14b",
            messages=[
                {
                    "role": "system",
                    "content": content
                },
                {
                    "role": "user",
                    "content": abstract
                }
            ],
            stream=False,
            options={
                'temperature': 0.2
            }
        )
        # Ensure that 'text' contains the string content of the message
        text = response['message']['content']
        return text
    except Exception as e:
        print(f"An error occurred: {e}")
        # Handle the error appropriately
        return None
    