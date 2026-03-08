import json
import os
import re
import requests
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .data import (
    SYMPTOM_LIST,
    DISEASE_SYMPTOM_MAP,
    DISEASE_DESCRIPTIONS,
    DISEASE_PRECAUTIONS,
    SYMPTOM_SEVERITY,
)
from .models import Consultation

# Dummy users (same as lib/auth-context.tsx)
DUMMY_USERS = [
    {"email": "admin@grammacare.com", "password": "admin123", "name": "Dr. Admin"},
    {"email": "doctor@grammacare.com", "password": "doctor123", "name": "Dr. Smith"},
    {"email": "patient@grammacare.com", "password": "patient123", "name": "John Doe"},
    {"email": "demo@grammacare.com", "password": "demo123", "name": "Demo User"},
]

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash-lite"
AI_NAME = "GrammaCare AI"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SYSTEM_INSTRUCTION = f"""
You are {AI_NAME} — a compassionate, experienced virtual healthcare assistant.

COMMUNICATION STYLE:
- Warm, empathetic, and reassuring — never robotic or clinical
- Use simple, easy-to-understand language (no heavy medical jargon)
- Always address the patient by their name
- Structure your responses clearly but conversationally — like a caring doctor would
- Always remind the patient that you are an AI and they should consult a real doctor for serious concerns
- Never be alarmist — be honest but kind and supportive
- Your name is {AI_NAME} — refer to yourself by this name when needed

RESPONSE FORMATTING RULES (STRICTLY FOLLOW):
1. Use consistent markdown formatting:
   - Use **bold** for important terms, drug names, and hospital names
   - Use bullet points (-) for lists, not numbered lists unless ordering matters
   - Use clear section headers with **Header:** format
   - Keep paragraphs short (2-3 sentences max)

2. Structure all responses consistently:
   - Start with a brief, warm acknowledgment addressing the patient
   - Present information in clear, organized sections
   - End with a supportive closing or next step

3. For medical recommendations:
   - Always list specific, real medication/hospital names when asked
   - Include dosage guidance only for OTC medications
   - Always mention when to seek professional help

4. NEVER:
   - Use different formats for the same type of information
   - Provide vague or generic responses when specifics are requested
   - Make up hospital names, drug names, or contact information
   - Skip sections that were requested in the prompt
"""


def ask_gemini(prompt: str, patient_name: str = "") -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        return f"[{AI_NAME} Error: Please configure GEMINI_API_KEY in your environment variables. Get a free API key from https://aistudio.google.com/apikey]"
    try:
        full_prompt = f"Patient name: {patient_name}\n\n{prompt}" if patient_name else prompt
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
        }
        url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        result = resp.json()
        if result.get("error"):
            err = result["error"]
            return f"[API Error {err.get('code', '')}: {err.get('message', 'Unknown error')}]"
        text = (result.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return (text or f"[{AI_NAME} temporarily unavailable]").strip()
    except Exception as e:
        return f"[{AI_NAME} temporarily unavailable: {e}]"


def symptom_display(s: str) -> str:
    return s.replace("_", " ").title()


def check_pattern(input_str: str):
    normalized = input_str.lower().replace(" ", "_")
    try:
        regex = re.compile(normalized, re.I)
        return [s for s in SYMPTOM_LIST if regex.search(s)]
    except re.error:
        return [s for s in SYMPTOM_LIST if normalized in s]


def calculate_severity_score(symptoms: list, days: int):
    if not symptoms:
        return {"score": 0, "is_severe": False, "level": "Unknown"}
    total = sum(SYMPTOM_SEVERITY.get(s, 0) for s in symptoms)
    score = (total * days) / (len(symptoms) + 1)
    if score > 13:
        return {"score": score, "is_severe": True, "level": "High"}
    if score > 7:
        return {"score": score, "is_severe": False, "level": "Moderate"}
    return {"score": score, "is_severe": False, "level": "Low"}


def get_related_symptoms_and_disease(symptom: str):
    mapping = DISEASE_SYMPTOM_MAP.get(symptom)
    if mapping:
        related = [s for s in mapping["related_symptoms"] if s != symptom]
        return {"disease": mapping["disease"], "related_symptoms": related}
    return {"disease": "Unknown condition", "related_symptoms": []}


def _reverse_geocode(lat: float, lon: float):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=14&addressdetails=1"
        resp = requests.get(url, headers={"User-Agent": "GrammaCare-AI/1.0"}, timeout=5)
        data = resp.json()
        if data and data.get("address"):
            addr = data["address"]
            return {
                "area": addr.get("suburb") or addr.get("neighbourhood") or addr.get("village") or addr.get("town") or "",
                "city": addr.get("city") or addr.get("town") or addr.get("municipality") or "",
                "region": addr.get("state") or addr.get("state_district") or "",
                "country": addr.get("country") or "",
            }
    except Exception:
        pass
    return None


# ─── Auth views ─────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def login_view(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    for u in DUMMY_USERS:
        if u["email"].lower() == email.lower() and u["password"] == password:
            request.session["user"] = {"email": u["email"], "name": u["name"]}
            return JsonResponse({"success": True, "user": {"email": u["email"], "name": u["name"]}})
    return JsonResponse({"success": False, "error": "Invalid email or password."}, status=401)


@csrf_exempt
@require_http_methods(["POST"])
def logout_view(request):
    request.session.flush()
    return JsonResponse({"success": True})


@csrf_exempt
@require_http_methods(["GET"])
def user_view(request):
    user = request.session.get("user")
    if not user:
        return JsonResponse({"authenticated": False}, status=401)
    return JsonResponse({"authenticated": True, "user": user})


# ─── Chat view ─────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def chat_view(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    action = body.get("action")
    patient_name = body.get("patientName") or ""
    symptom = body.get("symptom") or ""
    data = body.get("data") or {}
    lat = body.get("lat")
    lon = body.get("lon")
    location_source = body.get("locationSource", "")

    if action == "greeting":
        msg = ask_gemini(
            f"Give a warm, friendly greeting to the patient named {patient_name} as {AI_NAME}. "
            "Welcome them to the health consultation. Tell them they can describe their main symptom "
            "and you'll guide them through the rest. Keep it to 3-4 sentences. Be warm and reassuring.",
            patient_name,
        )
        return JsonResponse({"message": msg})

    if action == "ask_symptom":
        msg = ask_gemini(
            f"As {AI_NAME}, politely ask the patient {patient_name} to tell you their main symptom. "
            "Encourage them to describe it in simple terms (e.g., cough, fever, itching, headache). "
            "Keep it to 2-3 sentences. Friendly and inviting tone.",
            patient_name,
        )
        return JsonResponse({"message": msg})

    if action == "match_symptom":
        matches = check_pattern(symptom)
        return JsonResponse({
            "matches": [{"name": m, "display": symptom_display(m)} for m in matches],
        })

    if action == "get_followup_symptoms":
        selected = (data.get("selectedSymptom") or "").strip()
        result = get_related_symptoms_and_disease(selected)
        return JsonResponse({
            "disease": result["disease"],
            "relatedSymptoms": [{"name": s, "display": symptom_display(s)} for s in result["related_symptoms"]],
        })

    if action == "diagnose":
        primary_symptom = data.get("selectedSymptom") or ""
        days = data.get("days", 0)
        confirmed = data.get("confirmedSymptoms") or []
        primary_disease = data.get("disease") or ""
        all_symptoms = [primary_symptom] + [s for s in confirmed if s]
        sev = calculate_severity_score(all_symptoms, days)
        description = DISEASE_DESCRIPTIONS.get(primary_disease, "No description available.")
        precautions = DISEASE_PRECAUTIONS.get(primary_disease, [])
        second_disease = primary_disease
        same = primary_disease == second_disease
        symptoms_str = ", ".join(symptom_display(s) for s in all_symptoms)
        precautions_str = ", ".join(precautions)
        diagnosis = ask_gemini(
            f"You are {AI_NAME} giving a diagnosis summary to patient {patient_name}.\n\n"
            f"Primary diagnosis  : {primary_disease}\n"
            f"Secondary diagnosis: {'Same as primary -- both models agree, high confidence!' if same else second_disease}\n"
            f"Disease description: {description}\n\n"
            f"Symptoms the patient reported: {symptoms_str}\n"
            f"Duration  : {days} day(s)\n"
            f"Severity  : {sev['level']} (computed score: {sev['score']:.1f}/20)\n"
            f"Precautions from database: {precautions_str}\n\n"
            "Write a warm, doctor-patient style diagnosis report covering:\n"
            f"1. A reassuring opening addressing {patient_name} by name\n"
            "2. What they may have — explained in very simple, everyday language\n"
            "3. What this condition means for their daily life\n"
            f"4. Severity level explained clearly (what {sev['level']} means for them personally)\n"
            "5. Recommended precautions — rephrase the database precautions warmly, not robotically\n"
            f"6. A closing note reminding them {AI_NAME} is an AI and encouraging them to see a real doctor\n\n"
            "Use light formatting — bullet points only for precautions. Keep tone warm and human.",
            patient_name,
        )
        return JsonResponse({
            "diagnosis": diagnosis,
            "disease": primary_disease,
            "severityLevel": sev["level"],
            "severityScore": sev["score"],
            "isSevere": sev["is_severe"],
            "precautions": precautions,
        })

    if action == "otc_recommendations":
        otc_disease = data.get("disease") or ""
        severity_level = data.get("severityLevel") or ""
        location_str = "their area"
        if lat is not None and lon is not None:
            geo = _reverse_geocode(float(lat), float(lon))
            if geo:
                location_str = ", ".join(filter(None, [geo.get("area"), geo.get("city")])) or "their area"
        msg = ask_gemini(
            f"Patient {patient_name} has been tentatively diagnosed with: {otc_disease}\n"
            f"Severity: {severity_level}\n"
            f"Location: {location_str}\n\n"
            f"As {AI_NAME}, provide comprehensive medication guidance. Search your knowledge for REAL, commonly available medications.\n\n"
            "**OTC Medications (Available Without Prescription):**\n"
            "List 3-4 specific, REAL OTC drug names available in India/globally. For each:\n"
            "- **Drug Name** (Brand names in parentheses, e.g., Paracetamol (Crocin, Dolo 650))\n"
            "- Dosage: Standard adult dose\n"
            "- When to take: Timing and frequency\n"
            "- Price range: Approximate cost in INR\n\n"
            f"**Prescription Medications (Require Doctor's Prescription):**\n"
            f"If OTC medications are insufficient for {otc_disease}, list 2-3 prescription drugs that a doctor might prescribe.\n\n"
            "**Home Remedies:**\n"
            f"List 3 effective, practical home remedies specific to {otc_disease}\n\n"
            f"**Nearby Pharmacies in {location_str}:**\n"
            "Suggest 2-3 major pharmacy chains commonly found in India.\n\n"
            "**When to Stop Self-Medication and See a Doctor:**\n"
            f"Specific warning signs for {otc_disease} that require immediate medical attention.\n\n"
            "**Important Disclaimer:**\n"
            f"Remind {patient_name} that {AI_NAME} is an AI assistant - always verify with a healthcare professional.\n\n"
            "Keep the tone friendly, clear, and helpful.",
            patient_name,
        )
        return JsonResponse({"message": msg})

    if action == "find_hospitals":
        hosp_disease = data.get("disease") or ""
        location_str = "their current location (location could not be auto-detected)"
        location_info = {"source": "unknown"}

        if lat is not None and lon is not None and location_source == "gps":
            geo = _reverse_geocode(float(lat), float(lon))
            if geo:
                parts = [geo.get("area"), geo.get("city"), geo.get("region"), geo.get("country")]
                location_str = ", ".join(filter(None, parts))
                location_info = {
                    "lat": lat,
                    "lon": lon,
                    "area": geo.get("area"),
                    "city": geo.get("city"),
                    "region": geo.get("region"),
                    "country": geo.get("country"),
                    "source": "gps",
                }
            else:
                location_str = f"coordinates ({float(lat):.4f}, {float(lon):.4f})"
                location_info = {"lat": lat, "lon": lon, "source": "gps"}
        else:
            try:
                loc_resp = requests.get(
                    "http://ip-api.com/json/?fields=status,city,regionName,country,lat,lon,timezone,query",
                    timeout=5,
                )
                loc_data = loc_resp.json()
                if loc_data.get("status") == "success":
                    location_str = f"{loc_data.get('city', '')}, {loc_data.get('regionName', '')}, {loc_data.get('country', '')}"
                    location_info = {
                        "lat": loc_data.get("lat"),
                        "lon": loc_data.get("lon"),
                        "city": loc_data.get("city"),
                        "region": loc_data.get("regionName"),
                        "country": loc_data.get("country"),
                        "source": "ip",
                    }
            except Exception:
                pass

        coords_info = ""
        if location_info.get("lat") is not None and location_info.get("lon") is not None:
            coords_info = f"GPS Coordinates: {location_info['lat']:.6f}, {location_info['lon']:.6f}\n"
        area = location_info.get("area") or "a suburb"
        msg = ask_gemini(
            f"The patient {patient_name} has been diagnosed with: {hosp_disease}\n"
            f"Their detected location is: {location_str}\n"
            f"{coords_info}"
            f"Location source: {'Accurate GPS from browser' if location_info.get('source') == 'gps' else 'Approximate IP-based location'}\n\n"
            f"As {AI_NAME}, do the following:\n\n"
            f"1. Identify the best type of specialist/hospital department they should visit for {hosp_disease}\n\n"
            f"2. Suggest 4-5 well-known, reputable hospitals or healthcare facilities NEAR {location_str} "
            f"that would be appropriate for treating {hosp_disease}. "
            f"Focus on hospitals in or near {area} area specifically.\n\n"
            "Format each hospital as:\n"
            "**[Hospital Name]**\n"
            "- Location: [Specific area/locality]\n"
            "- Department: [relevant department to visit]\n"
            "- Distance: [Approximate if known]\n"
            "- Contact: [General hospital helpline if commonly known]\n"
            "- Why recommended: [one short reason]\n\n"
            "3. Add practical tips: what to carry, best time to visit, call ahead to confirm.\n\n"
            "IMPORTANT: Only suggest real, verifiable hospitals that actually exist in the mentioned location. Do NOT make up hospital names.\n\n"
            f"Keep the tone warm and reassuring as {AI_NAME}. Address the patient by name.",
            patient_name,
        )
        return JsonResponse({"message": msg, "location": location_info})

    if action == "farewell":
        farewell_dis = data.get("disease") or "their health concern"
        msg = ask_gemini(
            f"Give a warm goodbye message as {AI_NAME} to patient {patient_name} who consulted about {farewell_dis}. "
            "Wish them a speedy recovery, remind them to follow the precautions, "
            "and encourage them to visit a real doctor. Keep it to 2-3 sentences. Warm and hopeful.",
            patient_name,
        )
        return JsonResponse({"message": msg})

    if action == "free_chat":
        message = data.get("message") or ""
        msg = ask_gemini(
            f'The patient {patient_name} says: "{message}"\n\n'
            f"As {AI_NAME}, respond helpfully. If it's a health-related question, provide guidance. "
            "If they want to start a new consultation, guide them. Keep it conversational and warm.",
            patient_name,
        )
        return JsonResponse({"message": msg})

    return JsonResponse({"error": "Unknown action"}, status=400)


# ─── History: single endpoint that dispatches by method and action ─────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def history_view(request):
    if request.method == "GET":
        if request.GET.get("action") == "list":
            return history_list(request)
        if request.GET.get("action") == "get":
            return history_get(request)
        return JsonResponse({"error": "Invalid action"}, status=400)
    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        if body.get("action") == "save":
            return history_save(request)
        if body.get("action") == "delete":
            return history_delete(request)
        return JsonResponse({"error": "Invalid action"}, status=400)
    return JsonResponse({"error": "Method not allowed"}, status=405)


def history_list(request):
    username = (request.GET.get("username") or "").strip()
    if not username:
        return JsonResponse({"consultations": []})
    qs = Consultation.objects.filter(username__iexact=username).order_by("-date")
    consultations = [
        {
            "id": c.consultation_id,
            "date": c.date.isoformat() if hasattr(c.date, "isoformat") else str(c.date),
            "username": c.username,
            "symptom": c.symptom,
            "disease": c.disease,
            "severityLevel": c.severity_level,
            "messages": c.messages,
        }
        for c in qs
    ]
    return JsonResponse({"consultations": consultations})


@csrf_exempt
@require_http_methods(["GET"])
def history_get(request):
    cid = request.GET.get("id", "").strip()
    if not cid:
        return JsonResponse({"error": "Missing id"}, status=400)
    try:
        c = Consultation.objects.get(consultation_id=cid)
    except Consultation.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    return JsonResponse({
        "id": c.consultation_id,
        "date": c.date.isoformat() if hasattr(c.date, "isoformat") else str(c.date),
        "username": c.username,
        "symptom": c.symptom,
        "disease": c.disease,
        "severityLevel": c.severity_level,
        "messages": c.messages,
    })


@csrf_exempt
@require_http_methods(["POST"])
def history_save(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if body.get("action") != "save":
        return JsonResponse({"error": "Invalid action"}, status=400)
    consultation = body.get("consultation") or {}
    cid = (consultation.get("id") or "").strip()
    if not cid:
        return JsonResponse({"error": "Missing consultation id"}, status=400)
    from datetime import datetime
    date_val = consultation.get("date")
    if isinstance(date_val, str):
        try:
            date_val = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
        except ValueError:
            date_val = None
    if date_val is None:
        date_val = timezone.now()
    defaults = {
        "username": consultation.get("username", ""),
        "symptom": consultation.get("symptom", ""),
        "disease": consultation.get("disease", ""),
        "severity_level": consultation.get("severityLevel", ""),
        "messages": consultation.get("messages", []),
        "date": date_val,
    }
    Consultation.objects.update_or_create(consultation_id=cid, defaults=defaults)
    return JsonResponse({"success": True, "id": cid})


@csrf_exempt
@require_http_methods(["POST"])
def history_delete(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if body.get("action") != "delete":
        return JsonResponse({"error": "Invalid action"}, status=400)
    cid = (body.get("id") or "").strip()
    if not cid:
        return JsonResponse({"error": "Missing id"}, status=400)
    deleted, _ = Consultation.objects.filter(consultation_id=cid).delete()
    return JsonResponse({"success": True, "deleted": deleted})
