let recognition = null;
let isRecording = false;
let autoSpeak = false;
    
function initSpeechRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';
        
        recognition.onstart = function() {
            isRecording = true;
            document.getElementById('voiceButton').textContent = 'Stop';
            document.getElementById('voiceButton').className = 'bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded mr-2';
        };
        
        recognition.onresult = function(event) {
            const transcript = event.results[0][0].transcript;
            document.getElementById('messageInput').value = transcript;
            sendMessage();
        };
        
        recognition.onend = function() {
            isRecording = false;
            document.getElementById('voiceButton').textContent = 'Speak';
            document.getElementById('voiceButton').className = 'bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded mr-2';
        };
        
        recognition.onerror = function(event) {
            onsole.error('Speech recognition error:', event.error);
            isRecording = false;
            document.getElementById('voiceButton').textContent = 'Speak';
            document.getElementById('voiceButton').className = 'bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded mr-2';
        };
    } else {
        console.warn('Speech recognition not supported in this browser');
        document.getElementById('voiceButton').disabled = true;
        document.getElementById('voiceButton').textContent = 'Not supported';
    }
}
    
function toggleVoiceRecording() {
    if (!recognition) {
        alert('Speech recognition not supported in this browser');
        return;
    }
      
    if (isRecording) {
        recognition.stop();
    } else {
        recognition.start();
    }
}
    
function toggleAutoSpeak() {
    autoSpeak = !autoSpeak;
    const button = document.getElementById('autoSpeakButton');
    if (autoSpeak) {
        button.textContent = 'Auto-speak ON';
        button.className = 'bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded';
    } else {
        button.textContent = 'Auto-speak';
        button.className = 'bg-blue-600 hover:bg-purple-700 text-white px-4 py-2 rounded';
    }
}
    

function speakText(text) {
    if ('speechSynthesis' in window) {

        speechSynthesis.cancel();
        
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9;
        utterance.pitch = 1;
        utterance.volume = 1;
        
        // Try to use a more natural voice
        const voices = speechSynthesis.getVoices();
        const preferredVoice = voices.find(voice => 
          voice.name.includes('Google') || 
          voice.name.includes('Microsoft') ||
          voice.lang.startsWith('en')
        );
        if (preferredVoice) {
          utterance.voice = preferredVoice;
        }
        
        speechSynthesis.speak(utterance);
    } else {
        console.warn('Text-to-speech not supported in this browser');
    }
}
    
function showLoading() {
    document.getElementById('loadingSpinner').classList.remove('hidden');
    document.getElementById('sendButton').disabled = true;
    document.getElementById('sendButton').textContent = 'Sending...';
}
    
function hideLoading() {
    document.getElementById('loadingSpinner').classList.add('hidden');
    document.getElementById('sendButton').disabled = false;
    document.getElementById('sendButton').textContent = 'Send';
}

async function sendMessage() {
    let input = document.getElementById("messageInput");
    let message = input.value;
    let responseDiv = document.getElementById("response");

    input.value = '';

    showLoading();

    try {
        const res = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: message })
        });

        const data = await res.json();
        if (data.response) {
            responseDiv.textContent = "Bot: " + data.response;
        } else {
            responseDiv.textContent = "Error: " + (data.error || "Unknown error");
        }
    } catch (error) {
        responseDiv.textContent = "Error: Network error or server unavailable";
        console.error('Fetch error:', error);
    } finally {
        hideLoading();
    }
}