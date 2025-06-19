async function sendMessage() {
    const message = document.getElementById("messageInput").value;
    const responseDiv = document.getElementById("response");

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
  }