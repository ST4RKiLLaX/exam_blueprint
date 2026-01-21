from app.agents.agent import generate_reply

email = "Are there any classes in Manhattan? What is the cost?"
reply = generate_reply(email, history=[
    {"role": "user", "content": "Hi, I'm looking into CNA classes."},
    {"role": "assistant", "content": "Sure, happy to help! Where are you located?"},
])
print("📧 Question:", email)
print("\n🤖 Reply:\n")
print(reply)