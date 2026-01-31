/**
 * =============================================================================
 * RASA Chatbot Widget
 * =============================================================================
 * Embeddable chat widget for any website
 * 
 * Usage:
 *   <script>
 *     window.CHATBOT_CONFIG = {
 *       serverUrl: 'http://localhost:5005',
 *       title: 'Chat Support',
 *       subtitle: 'Ask me anything!',
 *       primaryColor: '#667eea'
 *     };
 *   </script>
 *   <script src="chatbot-widget.js"></script>
 * =============================================================================
 */

(function() {
    'use strict';

    // Configuration with defaults
    const config = Object.assign({
        serverUrl: 'http://localhost:5005',
        title: 'Chat Support',
        subtitle: 'We usually reply instantly',
        primaryColor: '#667eea',
        position: 'right', // 'left' or 'right'
        welcomeMessage: 'Hello! 👋 How can I help you today?',
        placeholder: 'Type a message...',
        userId: 'user_' + Math.random().toString(36).substr(2, 9)
    }, window.CHATBOT_CONFIG || {});

    // Inject styles
    const styles = `
        #chatbot-widget-container * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        #chatbot-toggle-btn {
            position: fixed;
            bottom: 20px;
            ${config.position}: 20px;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: ${config.primaryColor};
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
            z-index: 9998;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.3s, box-shadow 0.3s;
        }

        #chatbot-toggle-btn:hover {
            transform: scale(1.05);
            box-shadow: 0 6px 20px rgba(0,0,0,0.3);
        }

        #chatbot-toggle-btn svg {
            width: 28px;
            height: 28px;
            fill: white;
        }

        #chatbot-toggle-btn .close-icon {
            display: none;
        }

        #chatbot-toggle-btn.open .chat-icon {
            display: none;
        }

        #chatbot-toggle-btn.open .close-icon {
            display: block;
        }

        #chatbot-window {
            position: fixed;
            bottom: 90px;
            ${config.position}: 20px;
            width: 380px;
            max-width: calc(100vw - 40px);
            height: 520px;
            max-height: calc(100vh - 120px);
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            z-index: 9999;
            display: none;
            flex-direction: column;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }

        #chatbot-window.open {
            display: flex;
            animation: chatbot-slide-up 0.3s ease;
        }

        @keyframes chatbot-slide-up {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        #chatbot-header {
            background: ${config.primaryColor};
            color: white;
            padding: 20px;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        #chatbot-header-avatar {
            width: 44px;
            height: 44px;
            background: rgba(255,255,255,0.2);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }

        #chatbot-header-info h3 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 2px;
        }

        #chatbot-header-info p {
            font-size: 12px;
            opacity: 0.9;
        }

        #chatbot-messages {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            background: #f9fafb;
        }

        .chatbot-message {
            max-width: 85%;
            padding: 12px 16px;
            border-radius: 16px;
            line-height: 1.5;
            font-size: 14px;
            word-wrap: break-word;
        }

        .chatbot-message.user {
            background: ${config.primaryColor};
            color: white;
            align-self: flex-end;
            border-bottom-right-radius: 4px;
        }

        .chatbot-message.bot {
            background: white;
            color: #333;
            align-self: flex-start;
            border-bottom-left-radius: 4px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }

        .chatbot-typing {
            display: flex;
            gap: 4px;
            padding: 12px 16px;
            background: white;
            border-radius: 16px;
            border-bottom-left-radius: 4px;
            align-self: flex-start;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }

        .chatbot-typing span {
            width: 8px;
            height: 8px;
            background: #bbb;
            border-radius: 50%;
            animation: chatbot-typing 1.4s infinite ease-in-out both;
        }

        .chatbot-typing span:nth-child(1) { animation-delay: -0.32s; }
        .chatbot-typing span:nth-child(2) { animation-delay: -0.16s; }

        @keyframes chatbot-typing {
            0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
            40% { transform: scale(1); opacity: 1; }
        }

        #chatbot-input-container {
            padding: 16px;
            background: white;
            border-top: 1px solid #eee;
            display: flex;
            gap: 10px;
        }

        #chatbot-input {
            flex: 1;
            padding: 12px 16px;
            border: 1px solid #ddd;
            border-radius: 24px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }

        #chatbot-input:focus {
            border-color: ${config.primaryColor};
        }

        #chatbot-send-btn {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            background: ${config.primaryColor};
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }

        #chatbot-send-btn:hover {
            background: ${config.primaryColor}dd;
        }

        #chatbot-send-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }

        #chatbot-send-btn svg {
            width: 20px;
            height: 20px;
            fill: white;
        }

        #chatbot-powered-by {
            text-align: center;
            padding: 8px;
            font-size: 11px;
            color: #999;
            background: white;
        }

        @media (max-width: 480px) {
            #chatbot-window {
                width: calc(100vw - 20px);
                height: calc(100vh - 100px);
                bottom: 80px;
                ${config.position}: 10px;
                border-radius: 12px;
            }

            #chatbot-toggle-btn {
                width: 54px;
                height: 54px;
                bottom: 16px;
                ${config.position}: 16px;
            }
        }
    `;

    const styleSheet = document.createElement('style');
    styleSheet.textContent = styles;
    document.head.appendChild(styleSheet);

    // Create widget HTML
    const widgetHTML = `
        <div id="chatbot-widget-container">
            <button id="chatbot-toggle-btn" aria-label="Toggle chat">
                <svg class="chat-icon" viewBox="0 0 24 24">
                    <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/>
                </svg>
                <svg class="close-icon" viewBox="0 0 24 24">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                </svg>
            </button>
            <div id="chatbot-window">
                <div id="chatbot-header">
                    <div id="chatbot-header-avatar">🤖</div>
                    <div id="chatbot-header-info">
                        <h3>${config.title}</h3>
                        <p>${config.subtitle}</p>
                    </div>
                </div>
                <div id="chatbot-messages">
                    <div class="chatbot-message bot">${config.welcomeMessage}</div>
                </div>
                <div id="chatbot-input-container">
                    <input type="text" id="chatbot-input" placeholder="${config.placeholder}">
                    <button id="chatbot-send-btn" aria-label="Send message">
                        <svg viewBox="0 0 24 24">
                            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                        </svg>
                    </button>
                </div>
                <div id="chatbot-powered-by">Powered by RASA</div>
            </div>
        </div>
    `;

    // Inject widget
    const container = document.createElement('div');
    container.innerHTML = widgetHTML;
    document.body.appendChild(container.firstElementChild);

    // Get elements
    const toggleBtn = document.getElementById('chatbot-toggle-btn');
    const chatWindow = document.getElementById('chatbot-window');
    const messagesContainer = document.getElementById('chatbot-messages');
    const input = document.getElementById('chatbot-input');
    const sendBtn = document.getElementById('chatbot-send-btn');

    // Toggle chat window
    toggleBtn.addEventListener('click', () => {
        toggleBtn.classList.toggle('open');
        chatWindow.classList.toggle('open');
        if (chatWindow.classList.contains('open')) {
            input.focus();
        }
    });

    // Send message
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // Add user message
        addMessage(text, 'user');
        input.value = '';
        sendBtn.disabled = true;

        // Show typing indicator
        const typingIndicator = document.createElement('div');
        typingIndicator.className = 'chatbot-typing';
        typingIndicator.innerHTML = '<span></span><span></span><span></span>';
        messagesContainer.appendChild(typingIndicator);
        scrollToBottom();

        try {
            const response = await fetch(`${config.serverUrl}/webhooks/rest/webhook`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sender: config.userId,
                    message: text
                })
            });

            const data = await response.json();

            // Remove typing indicator
            typingIndicator.remove();

            // Add bot responses
            if (data && data.length > 0) {
                data.forEach(msg => {
                    if (msg.text) {
                        addMessage(msg.text, 'bot');
                    }
                    if (msg.buttons) {
                        // Handle quick reply buttons if needed
                        msg.buttons.forEach(btn => {
                            addMessage(`[${btn.title}]`, 'bot');
                        });
                    }
                });
            } else {
                addMessage("I didn't quite understand that. Could you rephrase?", 'bot');
            }

        } catch (error) {
            typingIndicator.remove();
            addMessage("Sorry, I'm having trouble connecting. Please try again later.", 'bot');
            console.error('Chatbot error:', error);
        }

        sendBtn.disabled = false;
        input.focus();
    }

    // Add message to chat
    function addMessage(text, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chatbot-message ${type}`;
        messageDiv.textContent = text;
        messagesContainer.appendChild(messageDiv);
        scrollToBottom();
    }

    // Scroll to bottom of messages
    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Event listeners
    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    // Expose API for advanced usage
    window.ChatbotWidget = {
        open: () => {
            toggleBtn.classList.add('open');
            chatWindow.classList.add('open');
        },
        close: () => {
            toggleBtn.classList.remove('open');
            chatWindow.classList.remove('open');
        },
        toggle: () => toggleBtn.click(),
        sendMessage: (text) => {
            input.value = text;
            sendMessage();
        },
        config: config
    };

})();
