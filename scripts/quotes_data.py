"""
💬 Quotes Data — Citations pour l'accueil Professor+
Hadiths authentiques + Citations de vie
"""

import random

HADITHS = [
    {"text": "La pudeur fait partie de la foi.", "source": "Al-Bukhari & Muslim", "narrator": "Ibn Umar"},
    {"text": "La foi comporte de nombreuses branches; la plus haute est l'affirmation de l'unicité d'Allah, et enlever une nuisance du chemin en fait partie.", "source": "Al-Bukhari & Muslim", "narrator": "Abu Hurairah"},
    {"text": "Les croyants sont comme un seul corps: si un membre souffre, tout le corps réagit.", "source": "Al-Bukhari & Muslim", "narrator": "An-Nu'man ibn Bashir"},
    {"text": "La foi n'est complète que lorsqu'on aime pour son frère ce qu'on aime pour soi-même.", "source": "Al-Bukhari & Muslim", "narrator": "Anas ibn Malik"},
    {"text": "Que celui qui croit en Allah et au Jour dernier ne nuise pas à son voisin, honore son invité, et dise du bien ou se taise.", "source": "Al-Bukhari & Muslim", "narrator": "Abu Hurairah"},
    {"text": "N'est pas pleinement croyant celui dont le voisin n'est pas à l'abri de son mal.", "source": "Al-Bukhari & Muslim", "narrator": "Abu Hurairah"},
    {"text": "Chaque matin, deux anges invoquent: l'un pour que le généreux soit remplacé dans ce qu'il donne, l'autre contre celui qui retient.", "source": "Al-Bukhari & Muslim", "narrator": "Abu Hurairah"},
    {"text": "Une bonne parole est une aumône.", "source": "Al-Bukhari & Muslim", "narrator": "Abu Hurairah"},
    {"text": "Parmi les meilleures œuvres en Islam: nourrir les gens et saluer ceux qu'on connaît comme ceux qu'on ne connaît pas.", "source": "Al-Bukhari & Muslim", "narrator": "Abdullah ibn Amr"},
    {"text": "La vérité mène à la droiture et la droiture mène au Paradis; le mensonge mène au mal et le mal mène au Feu.", "source": "Al-Bukhari & Muslim", "narrator": "Ibn Mas'ud"},
    {"text": "Quand Allah veut du bien à une personne, Il lui accorde la compréhension de la religion.", "source": "Al-Bukhari & Muslim", "narrator": "Mu'awiyah"},
    {"text": "Allah a écrit que Sa miséricorde l'emporte sur Sa colère.", "source": "Al-Bukhari & Muslim", "narrator": "Abu Hurairah"},
    {"text": "Allah a cent miséricordes; une seule a été envoyée ici-bas, et quatre-vingt-dix-neuf sont réservées pour le Jour de la Résurrection.", "source": "Al-Bukhari & Muslim", "narrator": "Abu Hurairah"},
    {"text": "Agissez avec bonté envers les femmes; la relation demande sagesse, douceur et compréhension.", "source": "Al-Bukhari & Muslim", "narrator": "Abu Hurairah"},
    {"text": "Le vrai musulman est celui dont les autres musulmans sont à l'abri de sa langue et de sa main.", "source": "Al-Bukhari & Muslim", "narrator": "Abdullah ibn Amr"},
    {"text": "Le musulman a des droits sur son frère: répondre au salut, visiter le malade, suivre le convoi funéraire, accepter l'invitation et répondre à l'éternuement.", "source": "Al-Bukhari & Muslim", "narrator": "Abu Hurairah"},
    {"text": "Jibril a tellement recommandé le bon comportement envers le voisin que le Prophète a cru qu'il allait lui donner un droit d'héritage.", "source": "Al-Bukhari & Muslim", "narrator": "Ibn Umar & Aisha"},
]

LIFE_QUOTES = [
    ("Profits are better than wages. Wages make you a living; profits make you a fortune.", "Jim Rohn"),
    ("Don't just let your business or your job make something for you; let it make something of you.", "Jim Rohn"),
    ("For things to change, you have to change.", "Jim Rohn"),
    ("Either you run the day or the day runs you.", "Jim Rohn"),
    ("Learn to work harder on yourself than you do on your job.", "Jim Rohn"),
    ("Success is not to be pursued; it is to be attracted by the person you become.", "Jim Rohn"),
    ("We must all suffer from one of two pains: the pain of discipline or the pain of regret.", "Jim Rohn"),
    ("Don't wish for less problems; wish for more skills.", "Jim Rohn"),
    ("Don't join an easy crowd; you won't grow.", "Jim Rohn"),
    ("Take care of your body. It's the only place you have to live.", "Jim Rohn"),
    ("You cannot change your destination overnight, but you can change your direction overnight.", "Jim Rohn"),
    ("Your attitude, not your aptitude, will determine your altitude.", "Zig Ziglar"),
    ("If you want to reach a goal, you must 'see the reaching' in your own mind before you actually arrive.", "Zig Ziglar"),
    ("A goal properly set is halfway reached.", "Zig Ziglar"),
    ("Success is not a destination, it's a journey.", "Zig Ziglar"),
    ("Positive thinking will let you do everything better than negative thinking will.", "Zig Ziglar"),
    ("Failure is the price of greatness.", "Robin Sharma"),
    ("Dream big, start small, begin today.", "Robin Sharma"),
    ("A leader is one who knows the way, goes the way, and shows the way.", "John Maxwell"),
    ("Personal growth is a leader's greatest silent investment.", "John Maxwell"),
    ("You have greatness within you.", "Les Brown"),
    ("Never let anyone's opinion of you become your reality.", "Les Brown"),
    ("Don't stop when you're tired, stop when you're done.", "David Goggins"),
    ("Be the leader you wish you had.", "Simon Sinek"),
    ("There are only two ways to influence human behavior: you can manipulate it or you can inspire it.", "Simon Sinek"),
    ("Happiness comes from WHAT we do. Fulfillment comes from WHY we do it.", "Simon Sinek"),
    ("Don't show up to prove. Show up to improve.", "Simon Sinek"),
    ("We achieve more when we chase the dream instead of the competition.", "Simon Sinek"),
    ("The more people you inspire, the more people will inspire you.", "Simon Sinek"),
    ("A community is a group of people who agree to grow together.", "Simon Sinek"),
    ("Building a strong culture is what builds a strong organization.", "Simon Sinek"),
    ("Solve people's problems and they'll pay you a fortune.", "Robin Sharma"),
    ("The best leaders are curious.", "Robin Sharma"),
    ("Effective communication is 20% what you know and 80% how you feel about what you know.", "Jim Rohn"),
    ("Your family and your love must be cultivated like a garden.", "Jim Rohn"),
]

PROGRESS_MESSAGES = {
    (0, 10): [
        "🧾 Les premiers règlements arrivent",
        "📋 C'est le début du cycle",
        "🌱 Les premières graines sont plantées",
        "⏳ Le mois démarre doucement",
    ],
    (10, 30): [
        "📬 Ça commence à se débloquer",
        "📨 Les paiements commencent à rentrer",
        "🔓 Le flux se met en place",
        "💧 Goutte à goutte, ça avance",
    ],
    (30, 50): [
        "📈 Belle progression ce mois-ci",
        "📊 On monte en régime",
        "💪 Le rythme est bon",
        "🌤️ L'horizon s'éclaircit",
    ],
    (50, 70): [
        "🚀 On passe un cap",
        "📊 Le mois avance bien",
        "💼 Bon rythme de règlements",
        "⚡ Les paiements s'enchaînent",
        "🟢 La situation est saine",
    ],
    (70, 90): [
        "🎯 Plus beaucoup avant la ligne d'arrivée",
        "🏃 Sprint final en approche",
        "⭐ Excellent taux de recouvrement",
        "🔥 On y est presque",
        "💎 Presque parfait",
    ],
    (90, 100): [
        "🏁 Derniers paiements en attente",
        "🎪 Il ne manque presque plus rien",
        "✨ Quasi complet",
        "🌟 Encore un petit effort",
    ],
    (100, 101): [
        "✅ Tous les paiements sont enregistrés",
        "🎉 Mois complet — bravo !",
        "🏆 100% encaissé — parfait !",
        "💯 Objectif atteint !",
    ],
}


def get_progress_message(pct):
    """Retourne un message aléatoire adapté au pourcentage."""
    for (low, high), messages in PROGRESS_MESSAGES.items():
        if low <= pct < high:
            return random.choice(messages)
    if pct >= 100:
        return random.choice(PROGRESS_MESSAGES[(100, 101)])
    return "📊 Suivi en cours"


def get_random_hadith(session_state=None):
    """Retourne un hadith aléatoire, en essayant de ne pas répéter."""
    used = []
    if session_state and "used_hadiths" in session_state:
        used = session_state["used_hadiths"]
    
    available = [i for i in range(len(HADITHS)) if i not in used]
    if not available:
        used.clear()
        available = list(range(len(HADITHS)))
    
    idx = random.choice(available)
    used.append(idx)
    
    if session_state is not None:
        session_state["used_hadiths"] = used
    
    return HADITHS[idx]


def get_random_life_quote(session_state=None):
    """Retourne une citation de vie aléatoire, en essayant de ne pas répéter."""
    used = []
    if session_state and "used_life_quotes" in session_state:
        used = session_state["used_life_quotes"]
    
    available = [i for i in range(len(LIFE_QUOTES)) if i not in used]
    if not available:
        used.clear()
        available = list(range(len(LIFE_QUOTES)))
    
    idx = random.choice(available)
    used.append(idx)
    
    if session_state is not None:
        session_state["used_life_quotes"] = used
    
    text, author = LIFE_QUOTES[idx]
    return {"text": text, "author": author}