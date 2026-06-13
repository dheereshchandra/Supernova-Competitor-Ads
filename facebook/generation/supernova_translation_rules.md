# Supernova — Localization / Translation Rules (v2 — FINALIZED 2026-06-12, pending test validation)

*The consolidated rules for replicating a team-approved ENGLISH master script into the 10 target
languages. Assembled per job as:*

```
translation prompt = §0 Contract + §1 Global rules (T1–T11) + §2 ONE format register module
                   + §3 ONE language module + its casting table
                   + per-ad block: edited English master (per scene) + unresolved Doc comments
                                 + characters w/ genders + seed-language name + target language
```

*At build time this file becomes `facebook/generation/supernova_translation_rules.md` (runtime-loaded,
same pattern as the creative context). Model: Flash first; escalate to Pro only if testing shows
Flash can't hold the register.*

---

## §0 — Contract

- **Input:** the team-edited English master (read live from the Google Doc — FROZEN TRUTH), its
  unresolved comments (binding instructions), ad metadata (production type, characters + genders,
  seed language, scene timings), one target language.
- **Output:** the same script scene-for-scene, line-for-line, in the target language — **ROMANIZED**
  (Latin script), code-mixed with English. Same scene count, order, labels. Images are reused
  unchanged; every line must keep fitting its visual.
- **Mandate:** translate + naturalize, never re-create. All creative latitude was spent in the
  English master. Only deviations these rules force are allowed (naturalness, casting, hook).
- *(Future context, NOT in scope now: after the romanized version is team-edited, a TTS input will
  be generated carrying BOTH code-mixed forms — Romanized+English and Native-script+English — and
  the better one per TTS engine gets picked. Design later.)*

## §1 — Global rules (override language modules)

**T1. Always code-mix.** Never pure native, never pure English.

**T2. The Stay-English list** (do NOT translate):
  a. **Any English being taught or quoted** — correction lines, example sentences, anything in `""`.
     Verbatim, always: the product IS English. Only the conversation around them moves.
     (City names INSIDE a quoted teaching line still re-cast per T6 — the line must stay believable
     for that viewer: Telugu version teaches "I am from Vijayawada", not "…Lucknow".)
  b. Grammar terms (tense, verb, sentence, pronunciation…).
  c. Brand + proper nouns: **Supernova, Miss Nova**, people names, app/platform names.
  d. Product vocabulary: "English", "Spoken English", "AI Teacher", app, install, download,
     practice, level, plan, interview.
  e. Daily-speech English: phone, office, computer, time, late, please, ready, help, correct,
     mistake, morning, job…
  f. Marketing abstractions whose native equivalent reads formal/Sanskritized: personalised,
     smart/smartly, confident, simple.
  g. Pleasantries: Perfect!, Thank you!, Good job!, Congrats!
  h. **Numbers stay numerals, English form:** "10–15 minutes", "1 crore+", "3 a.m.", "Day 15".
     Never spelled out in native words. "Crore" stays "crore" in ALL languages (no kodi/koti swap).
  i. Hyphenated English compounds stay whole: "job-interview", "level-test" — never half-translated.

**T3. Anti-newspaperish (the strongest rule).**
  - Spoken register ONLY: contractions, fragments, fillers ("just", "simply", "actually",
    yaar/machaan/anna where the language uses them), single-word lines ("Done.", "Easy.").
  - 5 simple words beat 12 polished ones, every time.
  - **Red flags → automatic rewrite:** literary/Sanskritized vocabulary; long compound nouns;
    textbook-perfect grammar where fragments are natural; news-anchor / government-notice /
    dubbed-film cadence.
  - **Mandatory read-aloud check** per scene: "friend on the phone" → keep; "news broadcaster" →
    rewrite.
  - **Self-critique pass:** after drafting, list every line that trips a red flag and rewrite it
    BEFORE returning. The returned script must be the post-critique version.

**T4. Politeness architecture (relationship-based, SEED-FAITHFUL).**
  - **Match the English master's address ENERGY.** If the English master speaks to the viewer
    BLUNTLY / tough-love (it often does — that's the winning hook), keep that blunt tier in the
    target language: the natural **direct-friend register** (Hindi/Gujarati/Bengali *tum*-tier,
    Telugu/Kannada/Malayalam/Tamil *nuvvu/nee*-tier) — NOT formal *aap*-tier, which makes a blunt
    line sound dubbed and dead (T3 violation). This is allowed and encouraged; it mirrors the
    relaxed hook rule of the English stage. Marathi note: *tu*-tier is naturally warm there — use it
    for blunt/peer address.
  - **Always polite** (aap / meeru / neenga / tumhi / neevu / ningal / apni / tame / apuni / tuseen):
    **every Miss Nova line** (she is always warm), and viewer-facing lines in ads whose English
    master is GENTLE/aspirational (not blunt). Never the *contemptuous/abusive* register — blunt
    friend, never rude stranger; insults are never allowed (G3).
  - Character-to-character dialogue matches the RELATIONSHIP: peers/friends use the natural middle
    register (friends saying "aap" to each other sounds dubbed); younger→elder respectful;
    elder→younger natural-warm. A mocking antagonist may use the harsh register ONLY where the
    English master already has mockery — and G3.1 still applies (shame must resolve in dignity).

**T5. Language self-reference swap.** Every language name inside the script resolves to the TARGET
language ("explains in Hindi" → "explains in Telugu" in the Telugu version); the mother-tongue
reframe (beat f) localizes the same way. A Telugu viewer never hears "Hindi".

**T6. Regional re-casting.**
  - Character names from the casting table (§3) — familiar everyday names, never distracting.
  - Cities/places re-localize to the language's region (tables in §3), INCLUDING inside quoted
    teaching lines (see T2a).
  - EXCEPTION: anything visibly forced by the reused visuals stays as shown.

**T7. The hook rule.** The first line is the thumbstop.
  - **DEFAULT: the hook opens in the native language. Always.** Do not open with English words.
  - **Sole exception — only when the script itself DEMANDS an English opening:** the opener IS
    quoted/taught English content that cannot exist any other way (the wrong-English line
    "I passed out in 2022!", a challenge like "Describe this in English!"). Then it stays per T2a.
    "Sounds nicer in English" is NOT a demand — when in doubt, open native.
  - If the English hook translates awkwardly, the model MAY reframe the first line — same context,
    same scene, same meaning, just natural and thumbstopping. This is the ONLY line with creative
    latitude.

**T8. Line-fit (visuals are frozen).** Each translated line ≈ same speech duration as its English
source (±20% syllables). Never merge, split, reorder, add, or drop scenes or speaking turns.

**T9. Edits + comments are law — with a safety override.** The edited English text is the source of
truth; unresolved Doc comments are binding instructions. If a comment conflicts with brand-safety
(e.g. asks for a hard rupee price), the guardrails win: **flag the conflict in the job output and
skip that instruction** — never silently obey, never fail the whole language for it.

**T10. Output format + romanization conventions.**
  - Scene labels, character names, parentheticals (shots/expressions) stay in English. Plain text;
    no markdown, no bold/asterisks.
  - Romanize the way Indians type in WhatsApp/chat: no diacritics, English-friendly spellings,
    standard contractions ("cheyandi", "pannunga", "karo", "korun"). Spell consistently within one
    script. Native-script EXAMPLES inside the language modules teach word choice and register —
    the OUTPUT is always romanized.

**T11. Brand safety is language-independent.** All guardrails (G1–G7 in
`supernova_brand_safety.md`) apply to every language version; the Flash safety audit runs on EVERY
localized script before it reaches the team. Wrong register toward the viewer (harsh singular) is
flagged as a G3 dignity issue.

## §2 — Format register modules (picked from the ad's production type)

| Format | Register tuning |
|---|---|
| **Teaching / correction skit** | Taught lines verbatim English (T2a). Miss Nova: warm, patient, polite plural. Learner: casual-respectful, self-deprecating but dignified. Explanations maximally colloquial. |
| **Authority / stage monologue** | Confident, measured; short punchy sentences; rhetorical questions; fewer fillers — still spoken, never literary. Slang dialed down. |
| **Friends / peer conversation** | Most colloquial; peer register (tum-tier), natural slang + fillers (yaar/machaan/anna); viewer-facing close still polite plural. |
| **Interview / talk-show** | Host: neutral-formal spoken. Guest (Miss Nova/expert): warm authority. Banter colloquial; English interview vocabulary stays. |
| **Family / narrative drama** | Kinship-correct honorifics per language (in-laws, elders). Emotion carried in the native language, never English. Shame lines extra-careful (G3.1). |
| **Mock news bulletin** | Anchor MAY be formal — the formality IS the joke — parody-light; payload lines stay colloquial. |
| **Whisper / intimate UGC** | Lowest formality, first-person confessional, fragments everywhere; "friend texting" energy. |

## §3 — Language modules (10) + casting tables

The per-language Rules 1–2 of the legacy prompts are now GLOBAL (T1/T2) and not repeated. Each
module = colloquial word forms (legacy Rule 3) + natural structure with examples (Rule 4) +
politeness forms (Rule 5, now governed by T4's relationship nuance) + a REGISTER BLOCK (Rule 6) +
casting table. Native-script examples teach register; output is romanized (T10).

> **Register-block status:** Tamil's block is complete (the gold standard). The other nine carry a
> seeded block of the same shape, to be enriched by each language owner from their first 2–3
> verified scripts — owner corrections get folded back into their language's block.

### 3.1 Hindi
- **Colloquial forms:** वो, ये, इसमें, क्या, यहाँ; spoken verb forms (कर रहा हूँ, करूँगा); never
  literary (करता हूँ over करता रहता हूँ where natural).
- **Structure examples (register reference):** "मैंने कल एक नई book खरीदी" · "Perfect! Bank में बैठे
  stranger को pen कैसे offer करोगे?" · "मैं घर पहुँचने पर आपको call करूँगा".
- **Politeness:** viewer/Miss Nova: आप + कीजिए/करिए/करो — never तू. Peers: तुम-tier.
- **Register block (seed):** prefer "try karna" over "इस्तेमाल/प्रयास करना"; "tension mat lo",
  "ho jayega", "bas itna hi"; red flag: any सम्पूर्ण/अत्यंत-class Sanskritized word.
- **Casting:** M: Rahul, Amit, Rohit, Saurabh, Vikas, Ankit, Manish, Deepak · F: Priya, Neha,
  Pooja, Anjali, Shweta, Ritu, Sakshi, Nisha · default pair **Rahul/Priya** · Cities: Lucknow,
  Kanpur, Delhi, Patna, Indore · Language name: "Hindi".

### 3.2 Telugu
- **Colloquial forms:** అది, ఇది, ఏమి, ఇక్కడ; spoken verbs (చేస్తున్నాను, వెళ్తున్నారు).
- **Structure examples:** "నేను నిన్న కొత్త book కొన్నాను" · "Perfect! Bank లో stranger కి pen ఎలా offer
  చెస్తరు?" · "నేను ఇంటికి reach అయిన తర్వాత మీకు call చేస్తాను".
- **Politeness:** viewer/Miss Nova: మీరు + -ండి ("download cheyandi") — never నువ్వు ("cheyi").
  Peers: natural mid-register.
- **Register block (seed):** "chala easy", "okka mistake kuda", "ayipoyindi"; red flag: bookish
  Sanskrit-Telugu compounds.
  - **GENDER AGREEMENT (native-review flag, 2026-06-12):** a FEMALE subject's negative/verb forms end
    **-dhu**, not the masculine **-du** — "Miss Nova ninnu judge **cheyyadhu**" / "ame andariki oke lesson
    **ivvadhu**" (NOT cheyadu / ivvadu). Flash gets this wrong by default — enforce it.
- **Casting:** M: Ramesh, Suresh, Ravi, Srinu, Mahesh, Venkat, Kiran, Sai · F: Lakshmi, Anusha,
  Swathi, Kavya, Priyanka, Sravani, Harika, Divya · default **Ravi/Lakshmi** · Cities: Hyderabad,
  Vijayawada, Warangal, Guntur · Language name: "Telugu".

### 3.3 Tamil — register block COMPLETE (gold standard)
- **Colloquial forms:** அத, இத, இதுல, இங்க; spoken verbs (பண்றேன், இருக்கு, வர்றேன்).
- **Structure examples:** "நான் நேத்து ஒரு புது book வாங்கினேன்" · "Perfect! Bank ல இருக்குற stranger
  கிட்ட எப்படி pen offer பண்ணுவீங்க?" · "நான் வீட்டுக்கு reach ஆனதும் உங்களுக்கு call பண்றேன்".
- **Politeness:** viewer/Miss Nova: நீங்க + -ங்க ("pannunga", "sollunga") — never நீ ("pannu").
- **Register block (FULL — Chennai-Madras Tanglish):**
  - Contractions always: வேண்டாம்→வேணாம் · ஆனால்→ஆனா · இருக்கிறது→இருக்கு · வருகிறேன்→வர்றேன் ·
    செய்கிறேன்→பண்றேன் · செய்கிறீர்கள்→பண்றீங்க · சொல்கிறேன்→சொல்றேன் · இருக்கிறேன்→இருக்கேன் ·
    போகிறேன்→போறேன் · கேட்கிறேன்→கேக்குறேன் · இல்லையா→இல்ல · இங்கே→இங்க · அங்கே→அங்க ·
    எவ்வாறு→எப்படி · மேலும்→இன்னும்.
  - Formal ✗ → Native ✓: "பயப்பட வேண்டாம்"→"payappadaatheenga / tension vidunga" · "எந்த தப்பும்
    இல்லாம"→"oru thappum illaama / oru mistake-um illaama" · "செய்ய வேண்டும்"→"pannanum" ·
    "உள்ளது"→"irukku" · "மாற்றும்"→"maathidum / convert-pannidum" · "தேவைப்படும்"→"venum /
    need-aagum".
  - Ad-voice particles: "thaan" for emphasis ("idhu-thaan!"), "appo/appram/so" connectors, "oru"
    before nouns, "udane", English "just", repetition for emphasis ("easy-aa easy-aa").
  - Red flags: compound verbs in "ஆகியிருக்கிறது/செய்துவருகிறது", Sanskritized vocab, full
    grammatical agreement where fragments are natural, news-anchor cadence.
- **Casting:** M: Karthik, Suresh, Prakash, Arjun, Vijay, Saravanan, Dinesh, Senthil · F: Priya,
  Kavitha, Divya, Lakshmi, Meena, Nithya, Revathi, Gayathri · default **Karthik/Kavitha** ·
  Cities: Chennai, Madurai, Coimbatore, Trichy · Language name: "Tamil".

### 3.4 Marathi
- **Colloquial forms:** spoken short forms (मला धावायचं आहे; ती गात असेल).
- **Structure examples:** "मी काल एक नवीन book घेतलं" · "तुम्हाला कोणती book वाचायला आवडेल?" ·
  "मी घरी पोहोचल्यावर तुला call करेन".
- **Politeness:** viewer/Miss Nova: तुम्ही + करा — never तू कर. Peers: natural अरे/अगं tone.
- **Register block (seed):** "ek number!", "bindhast bola", "kahi tension nahi"; red flag:
  शुद्ध-Marathi literary compounds.
- **Casting (proposed — confirm):** M: Sachin, Amol, Prasad, Nikhil, Swapnil, Sandeep, Vishal,
  Rohan · F: Pooja, Snehal, Prachi, Vaishnavi, Shraddha, Aarti, Madhuri, Manasi · default
  **Amol/Snehal** · Cities: Pune, Nagpur, Nashik, Aurangabad · Language name: "Marathi".

### 3.5 Bengali
- **Colloquial forms:** ওটা, এটা, কী, এখানে; spoken verbs (যাচ্ছে, খাচ্ছিল).
- **Structure examples:** "আমি একটা নতুন book কিনলাম" · "Perfect! ব্যাঙ্কে কোনো stranger কে কিভাবে একটা
  pen offer করবেন?" · "আমি বাড়ি পৌঁছে তোমাকে call করব".
- **Politeness:** viewer/Miss Nova: আপনি + করুন — never তুই. Peers: তুমি-tier.
- **Register block (seed):** "ekdom simple", "tension nio na", "hoye jabe"; red flag: সাধু-ভাষা /
  literary verb endings.
- **Casting (proposed — confirm):** M: Sourav, Arnab, Abhijit, Debashish, Sandip, Raju, Subho,
  Rana · F: Moumita, Ananya, Riya, Priyanka, Payel, Tania, Sudipta, Sraboni · default
  **Sourav/Moumita** · Cities: Kolkata, Howrah, Siliguri, Durgapur · Language name: "Bangla".

### 3.6 Malayalam
- **Colloquial forms:** അത്, ഇത്, എന്ത്, ഇവിടെ; spoken verbs (ചെയ്യുന്നു, പോകണം).
- **Structure examples:** "ഞാൻ ഇന്നലെ ഒരു പുതിയ book വാങ്ങി" · "Perfect! bank-ൽ ഇരിക്കുന്ന stranger-നോട്
  എങ്ങനെ pen offer ചെയ്യും?" · "ഞാൻ വീട്ടിൽ എത്തുമ്പോൾ നിങ്ങളെ call ചെയ്യും".
- **Politeness:** viewer/Miss Nova: നിങ്ങൾ + ചെയ്യൂ/ചെയ്യുക — never നീ ചെയ്യ്. Peers: natural
  മച്ചാനെ/അളിയാ tone where the format allows.
- **Register block (seed):** "pole", "alle", "okke", "scene illa", "adipoli"; red flag:
  Sanskritized formal Malayalam.
- **Casting:** M: Arun, Anoop, Suresh, Rajesh, Vishnu, Jithin, Akhil, Nikhil · F: Anu, Lakshmi,
  Divya, Arya, Athira, Sneha, Reshma, Aparna · default **Arun/Anu** · Cities: Kochi, Kozhikode,
  Thrissur, Thiruvananthapuram · Language name: "Malayalam".

### 3.7 Kannada
- **Colloquial forms:** ಅದು, ಇದು, ಏನು, ಇಲ್ಲಿ; spoken verbs (ಮಾಡ್ತಾ ಇದ್ದೀನಿ, ಹೋಗ್ತಾ ಇದ್ದಾರೆ).
- **Structure examples:** "ನಾನ್ ಇವತ್ತು park ಅಲ್ಲಿದ್ದಾಗ ಅವನ್ನ meet ಮಾಡ್ದೆ" · "ನೀವು ಯಾವ book ನ ಓದಕ್ಕೆ prefer
  ಮಾಡ್ತೀರಾ" · "ನಾನು ಮನೆಗೆ reach ಆದ್ಮೇಲೆ ನಿಮಗೆ call ಮಾಡ್ತೀನಿ".
- **Politeness:** viewer/Miss Nova: ನೀವು + ಮಾಡಿ — never ನೀನು ಮಾಡು. Peers: maga/guru tone where
  format allows.
- **Register block (seed):** "super aagide", "swalpa adjust maadi", "yen problem illa"; red flag:
  ಗ್ರಾಂಥಿಕ literary Kannada.
- **Casting:** M: Manjunath, Ramesh, Naveen, Kiran, Pradeep, Santhosh, Chethan, Lohith · F:
  Lakshmi, Asha, Kavya, Divya, Shruthi, Pooja, Sowmya, Rashmi · default **Manjunath/Asha** ·
  Cities: Bengaluru, Mysuru, Hubli, Mangaluru · Language name: "Kannada".

### 3.8 Gujarati
- **Colloquial forms:** spoken short forms (મારે દોડવું છે; તે study કરે છે).
- **Structure examples:** "મેં ગઈકાલે નવી book ખરીદી" · "તમે કઈ book વાંચવાનું prefer કરશો?" · "હું ઘરે
  પહોંચું ત્યારે તમને call કરીશ".
- **Politeness:** viewer/Miss Nova: તમે + કરો — never તું કર. Peers: natural યાર tone.
- **Register block (seed):** "ekdam mast", "tension na lo", "thai jashe"; red flag: શુદ્ધ literary
  Gujarati compounds.
- **Casting (proposed — confirm):** M: Hardik, Jignesh, Chirag, Mehul, Ketan, Parth, Ravi, Sanjay ·
  F: Hetal, Krupa, Dhwani, Nisha, Falguni, Jinal, Pooja, Bhavna · default **Hardik/Hetal** ·
  Cities: Ahmedabad, Surat, Rajkot, Vadodara · Language name: "Gujarati".

### 3.9 Assamese — includes the 4 grammar rules
- **Colloquial forms:** যে, এই, কি, ইয়াত; spoken verbs (গৈ আছে, খাই আছিল).
- **Structure examples:** "কালি মই এখন নতুন book কিনিছিলোঁ" · "আপুনি কোনখন book পঢ়িবলৈ prefer কৰে" ·
  "মই ঘৰত উপস্থিত হ'লে তোমাক call কৰিম".
- **Grammar rules (kept verbatim from the team prompt):**
  - Future perfect → simple future (no কৰি থাকিব).
  - Modal verbs (may/might/can/could/should/must) → Assamese equivalents (পাৰোঁ…), NOT English.
  - Weather conditionals → verb দিয়ে, not হয় ("যদি বৰষুণ দিয়ে…").
  - Tag questions → হয়নে?/নহয়নে?/নে? — never literal verb repetition.
- **Politeness:** viewer/Miss Nova: আপুনি + -ক/-ব — never তই. Peers: তুমি-tier.
- **Register block (seed):** to be enriched by the Assamese owner.
- **Casting (proposed — confirm):** M: Rupam, Ankur, Bikash, Dipankar, Manash, Pranjal, Jintu,
  Himangshu · F: Pallabi, Juri, Barsha, Nilakshi, Bhanita, Gitashree, Mridusmita, Priyanka ·
  default **Rupam/Pallabi** · Cities: Guwahati, Dibrugarh, Jorhat, Tezpur · Language name:
  "Assamese (Axomiya)".

### 3.10 Punjabi — includes the 4 syntax rules
- **Colloquial forms:** ਉਹ, ਇਹ, ਕੀ, ਇੱਥੇ; spoken verbs (ਜਾ ਰਹੇ ਹਨ, ਖਾ ਰਿਹਾ ਸੀ).
- **Structure examples:** "ਮੈਂ ਕੱਲ੍ਹ ਇੱਕ ਨਵੀਂ book ਖਰੀਦੀ" · "ਤੁਸੀਂ ਕਿਹੜੀ book ਪੜ੍ਹਨ ਲਈ prefer ਕਰੋਗੇ?" ·
  "ਮੈਂ ਘਰ ਪਹੁੰਚ ਕੇ ਤੁਹਾਨੂੰ call ਕਰਾਂਗਾ".
- **Syntax rules (kept verbatim):**
  - Gender + verb agreement matched to subject ("ਤੁਹਾਨੂੰ study ਕਰਨੀ ਚਾਹੀਦੀ ਹੈ").
  - Punjabi equivalents for places/situations (ਘਰ ਵਿੱਚ, not "home ਤੇ").
  - English nouns in relative clauses take ਜਿਸ/ਜੋ ("ਜਿਸ ਆਦਮੀ ਨੇ hat ਪਾਈ ਹੋਈ ਹੈ…").
  - No word-by-word literalism — preserve Punjabi flow ("ਮੈਂ ਹਰ ਦਿਨ ਪੜ੍ਹਦਾ ਹਾਂ", not "ਹਰ day").
- **Politeness:** viewer/Miss Nova: ਤੁਸੀਂ + -ੋ/-ੋਗੇ — never ਤੂੰ. Peers: natural ਯਾਰ tone.
- **Register block (seed):** "vadhiya!", "koi gal nahi", "ho jauga"; red flag: literary Punjabi.
- **Casting (proposed — confirm):** M: Gurpreet, Harpreet, Jaspreet, Manpreet, Karan, Amrit,
  Rajinder, Sukhdev · F: Simran, Harleen, Navjot, Kiran, Jasleen, Amrita, Gurleen, Raman ·
  default **Gurpreet/Simran** · Cities: Ludhiana, Amritsar, Jalandhar, Patiala · Language name:
  "Punjabi".

## §4 — QA gates (per language version, before it reaches the team)

1. **Stay-English audit** — taught/quoted lines byte-identical to the English master (except T6
   city re-cast); numerals intact.
2. **Casting check** — no source-language names/cities leaked; names from the table.
3. **Line-fit check** — ±20% syllable budget per line; scene/turn structure unchanged.
4. **Politeness check** — T4 register per line type (viewer / Miss Nova / character).
5. **Flash brand-safety audit** — full G1–G7 pass; BLOCK/FLAG semantics identical to English.
6. **Human verification** — by that language's owner (per-language verified_by); owner corrections
   feed back into that language's register block (§3).
