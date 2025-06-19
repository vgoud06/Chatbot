from flask import Flask, request, jsonify, render_template
from chatbot import Chatbot, ChatbotLanguageModel
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
chatbot = Chatbot()


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_input = data.get("message")
    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    try:
        response = chatbot.get_response(user_input)
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)

