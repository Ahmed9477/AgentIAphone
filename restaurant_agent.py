from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
import json
from datetime import datetime
import os
from dotenv import load_dotenv
from restaurant_config import RESTAURANT_NAME, RESTAURANT_DATA

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MEMORY_TIMEOUT = int(os.getenv("MEMORY_TIMEOUT", "1800"))  # 30 minutes

# Initialiser OpenAI
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ Client OpenAI initialisé avec succès")
except Exception as e:
    print(f"❌ Erreur lors de l'initialisation OpenAI: {e}")
    client = None

# Stockage des conversations avec timestamps
conversations = {}  # {call_sid: [{"role": str, "content": str, "time": datetime}]}


# ==================== FONCTIONS UTILITAIRES ====================

def cleanup_old_conversations():
    """Nettoie les conversations expirées ou trop longues"""
    now = datetime.now()
    to_delete = []

    for call_sid, conv in conversations.items():
        if not conv:
            to_delete.append(call_sid)
            continue

        # Supprimer si conversation trop longue (plus de 30 messages)
        if len(conv) > 30:
            to_delete.append(call_sid)
            continue

        # Supprimer si dernier message trop ancien
        last_message_time = conv[-1].get("time", now)
        if (now - last_message_time).seconds > MEMORY_TIMEOUT:
            to_delete.append(call_sid)

    for sid in to_delete:
        print(f"🗑️  Nettoyage conversation: {sid}")
        del conversations[sid]

    if to_delete:
        print(f"✅ {len(to_delete)} conversation(s) nettoyée(s)")


def detect_conversation_stage(history):
    """Détecte automatiquement l'étape de la conversation"""
    if len(history) < 4:
        return "commande"  # Prise de commande
    elif len(history) < 8:
        return "livraison"  # Type de livraison
    elif len(history) < 12:
        return "infos_client"  # Infos client
    else:
        return "finalisation"  # Finalisation


def extract_order_summary(history):
    """Extrait un résumé des articles commandés"""
    user_messages = [msg["content"] for msg in history if msg["role"] == "user"]

    if not user_messages:
        return "Nouvelle commande"

    # Prendre les 3 premiers messages utilisateur pour le contexte
    recent = " ".join(user_messages[:3])
    return recent[:100] + "..." if len(recent) > 100 else recent


def get_ai_response(history, user_input):
    """
    Génère une réponse IA avec mémoire contextuelle

    Args:
        history: Historique de la conversation (sans le dernier message user)
        user_input: Dernier message de l'utilisateur

    Returns:
        str: Réponse de l'assistant
    """

    # Détection automatique de l'étape
    stage = detect_conversation_stage(history)
    order_summary = extract_order_summary(history)

    # Construction du prompt système adaptatif
    system_prompt = f"""Tu es l'assistant vocal de {RESTAURANT_NAME}, un restaurant de fast-food.

📋 CONTEXTE ACTUEL:
• Commande en cours: {order_summary}
• Étape: {stage}
• Historique: {len(history)} messages

🎯 TON RÔLE:
1. Prendre la commande (articles, quantités, sauces)
2. Demander le type (sur place, emporter, livraison)
3. Recueillir les infos client (nom, téléphone)
4. Si livraison: demander l'adresse
5. Confirmer le paiement (espèces ou carte)
6. Faire un récapitulatif clair avec le total
7. Dire "Merci, à bientôt" et TOUJOURS terminer par END_CALL

✅ RÈGLES STRICTES:
• Maximum 15 mots par réponse
• Une seule question à la fois
• Rester sur le sujet de la commande
• Ton chaleureux et professionnel
• TOUJOURS se souvenir de ce qui a été dit avant
• Quand tout est clair, dire END_CALL pour terminer

❌ INTERDICTIONS:
• Ne jamais oublier les articles déjà commandés
• Ne jamais redemander ce qui a déjà été donné
• Ne pas inventer de prix ou d'articles
• Ne pas être trop bavard

📝 EXEMPLE DE CONVERSATION:
Client: "Un kebab"
Toi: "Quelle sauce pour votre kebab?"
Client: "Ketchup"
Toi: "Combien de kebabs?"
Client: "Deux"
Toi: "Autre chose?"
Client: "Non"
Toi: "Sur place, emporter ou livraison?"
Client: "Livraison"
Toi: "Votre nom?"
Client: "Ahmed"
Toi: "Votre numéro de téléphone?"
Client: "06 12 34 56 78"
Toi: "Votre adresse complète?"
Client: "5 rue de Paris"
Toi: "Espèces ou carte?"
Client: "Carte"
Toi: "2 kebabs sauce ketchup, livraison au 5 rue de Paris, Ahmed 0612345678, carte. Total 15 euros. Merci! END_CALL"
"""

    # Construction des messages pour l'API
    messages = [{"role": "system", "content": system_prompt}]

    # Ajouter les 10 derniers messages de l'historique (pour ne pas dépasser le contexte)
    messages.extend([
        {"role": msg["role"], "content": msg["content"]}
        for msg in history[-10:]
    ])

    # Ajouter le message actuel de l'utilisateur
    messages.append({"role": "user", "content": user_input})

    try:
        if client is None:
            return "Service temporairement indisponible. Veuillez rappeler."

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,  # Un peu de créativité mais reste cohérent
            max_tokens=80,  # Limiter la longueur
            timeout=3  # Timeout de 3 secondes
        )

        ai_reply = response.choices[0].message.content.strip()

        # Nettoyage de la réponse
        ai_reply = ai_reply.replace('"', '').replace('*', '')

        return ai_reply

    except Exception as e:
        print(f"❌ Erreur API OpenAI: {e}")

        # Réponse de secours selon l'étape
        fallback_responses = {
            "commande": "Que souhaitez-vous commander?",
            "livraison": "Sur place, emporter ou livraison?",
            "infos_client": "Votre nom et téléphone?",
            "finalisation": "Espèces ou carte?"
        }

        return fallback_responses.get(stage, "Pouvez-vous répéter?")


# ==================== ROUTES VOCALES ====================

@app.route("/voice", methods=["POST"])
def voice():
    """Point d'entrée initial de l'appel"""

    call_sid = request.values.get("CallSid", "unknown")[:8]
    caller = request.values.get("From", "inconnu")

    print(f"\n📞 NOUVEL APPEL - CallSid: {call_sid} - De: {caller}")

    response = VoiceResponse()
    response.say(
        f"Bonjour, bienvenue chez {RESTAURANT_NAME}! Que souhaitez-vous commander?",
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    # Gather pour capturer la réponse vocale
    gather = Gather(
        input="speech",
        language="fr-FR",
        speechTimeout="auto",  # Détection automatique de la fin de parole
        action="/process",
        method="POST",
        hints="pizza burger kebab tacos frites sandwich menu boisson livraison emporter",
        timeout=10
    )

    response.append(gather)

    # Si pas de réponse après le timeout
    response.say(
        "Je n'ai pas entendu votre réponse. Au revoir.",
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    return Response(str(response), mimetype="text/xml")


@app.route("/process", methods=["POST"])
def process():
    """Traite chaque réponse vocale du client"""

    speech = request.values.get("SpeechResult", "").strip()
    call_sid = request.values.get("CallSid", "unknown")[:8]
    confidence = request.values.get("Confidence", "0")

    print(f"\n📞 [{call_sid}] 👤 Client: '{speech}' (confiance: {confidence})")

    # Si pas de parole détectée
    if not speech:
        response = VoiceResponse()
        response.say(
            "Je n'ai pas compris. Pouvez-vous répéter?",
            language="fr-FR",
            voice="Google.fr-FR-Neural2-B"
        )

        gather = Gather(
            input="speech",
            language="fr-FR",
            speechTimeout="auto",
            action="/process",
            method="POST",
            timeout=10
        )
        response.append(gather)

        return Response(str(response), mimetype="text/xml")

    # Initialiser la conversation si nécessaire
    if call_sid not in conversations:
        conversations[call_sid] = []

    conv = conversations[call_sid]

    # Ajouter le message utilisateur avec timestamp
    conv.append({
        "role": "user",
        "content": speech,
        "time": datetime.now()
    })

    # Obtenir la réponse de l'IA
    ai_reply = get_ai_response(conv[:-1], speech)

    print(f"📞 [{call_sid}] 🤖 Bot: '{ai_reply}'")

    # Ajouter la réponse du bot avec timestamp
    conv.append({
        "role": "assistant",
        "content": ai_reply,
        "time": datetime.now()
    })

    # Vérifier si c'est la fin de la conversation
    should_end = "END_CALL" in ai_reply.upper()

    # Retirer END_CALL de la réponse vocale
    ai_reply_clean = ai_reply.replace("END_CALL", "").replace("end_call", "").strip()

    response = VoiceResponse()
    response.say(
        ai_reply_clean,
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    if should_end:
        # Terminer l'appel
        print(f"📴 [{call_sid}] ✅ APPEL TERMINÉ - Commande complète")
        response.hangup()

        # Sauvegarder la commande complète (optionnel)
        save_order(call_sid, conv)
    else:
        # Continuer la conversation
        gather = Gather(
            input="speech",
            language="fr-FR",
            speechTimeout="auto",
            action="/process",
            method="POST",
            timeout=10
        )
        response.append(gather)

        # Message si timeout
        response.say(
            "Êtes-vous toujours là? Au revoir.",
            language="fr-FR",
            voice="Google.fr-FR-Neural2-B"
        )

    # Nettoyage périodique
    cleanup_old_conversations()

    return Response(str(response), mimetype="text/xml")


def save_order(call_sid, conversation):
    """Sauvegarde la commande finale (optionnel)"""
    try:
        order_data = {
            "call_sid": call_sid,
            "timestamp": datetime.now().isoformat(),
            "conversation": conversation
        }

        # Créer le dossier orders s'il n'existe pas
        os.makedirs("orders", exist_ok=True)

        # Sauvegarder dans un fichier JSON
        filename = f"orders/order_{call_sid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(order_data, f, ensure_ascii=False, indent=2, default=str)

        print(f"💾 Commande sauvegardée: {filename}")

    except Exception as e:
        print(f"⚠️  Erreur sauvegarde commande: {e}")


# ==================== ROUTES API ====================

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def home():
    """Page d'accueil / Health check"""
    cleanup_old_conversations()

    return jsonify({
        "status": "online",
        "restaurant": RESTAURANT_NAME,
        "active_conversations": len(conversations),
        "ai_enabled": client is not None,
        "version": "2.0"
    })


@app.route("/api/stats", methods=["GET"])
def stats():
    """Statistiques du serveur"""
    cleanup_old_conversations()

    return jsonify({
        "restaurant": RESTAURANT_NAME,
        "conversations_actives": len(conversations),
        "total_messages": sum(len(conv) for conv in conversations.values()),
        "ai_status": "active" if client else "inactive"
    })


@app.route("/api/conversations", methods=["GET"])
def get_conversations():
    """Liste toutes les conversations actives"""
    cleanup_old_conversations()

    conversations_list = []
    for call_sid, conv in conversations.items():
        conversations_list.append({
            "call_sid": call_sid,
            "messages": len(conv),
            "last_activity": conv[-1]["time"].isoformat() if conv else None
        })

    return jsonify(conversations_list)


@app.route("/clear", methods=["POST"])
def clear():
    """Efface toutes les conversations"""
    global conversations
    count = len(conversations)
    conversations.clear()
    print(f"🗑️  {count} conversation(s) effacée(s)")

    return jsonify({
        "cleared": True,
        "count": count
    })


# ==================== MIDDLEWARE ====================

@app.after_request
def after_request(response):
    """Nettoyage automatique après chaque requête"""
    cleanup_old_conversations()
    return response


# ==================== LANCEMENT ====================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🍔 AGENT IA RESTAURANT - SYSTÈME VOCAL INTELLIGENT")
    print("=" * 60)
    print(f"🏪 Restaurant: {RESTAURANT_NAME}")
    print(f"🤖 IA: {'✅ Active (OpenAI)' if client else '❌ Inactive'}")
    print(f"🧠 Mémoire: {MEMORY_TIMEOUT // 60} minutes")
    print(f"🌐 URL locale: http://localhost:5000")
    print(f"📞 Webhook: http://votre-ngrok.com/voice")
    print("=" * 60)
    print("\n🚀 Serveur démarré - En attente d'appels...\n")

    app.run(debug=True, port=5000, host="0.0.0.0")