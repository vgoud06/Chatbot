from flask import Flask, request, jsonify, render_template
from chatbot import Chatbot, ChatbotLanguageModel
from flask_cors import CORS
from google.cloud import speech
import os
import io

app = Flask(__name__)
CORS(app)
chatbot = Chatbot()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/vivekgoud/Downloads/chatbot-463417-0f7060c3e52e.json"

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

@app.route("/upload_audio", methods=["POST"])
def upload_audio():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        audio_file = request.files['file']
        content = audio_file.read()

        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=44100,
            language_code="en-US",
        )

        response = client.recognize(config=config, audio=audio)
        transcript = " ".join([r.alternatives[0].transcript for r in response.results])
        return jsonify({"transcript": transcript})

    except Exception as e:
        print("❌ Error in /upload_audio:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)

