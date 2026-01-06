## 1. Formalization in **English**

### Title

**Voice Survey Agent** – AI Voice Agent for National and International Phone Surveys

### Vision

Build an AI voice agent that can place national and international phone calls, speak natural language, and politely persuade people to participate in a short 3-question survey. The agent should integrate with generative models (GPT, Claude, Gemini) and telephony providers, automatically handling call outcomes, retries, and follow-up emails.

### Problem Statement

Today, phone-based surveys rely heavily on human agents, which is expensive, hard to scale, and inconsistent in quality. It is also difficult to orchestrate:

* multiple call attempts,
* handling busy/no-answer states,
* sending confirmation or closure emails,
* collecting and structuring responses.

We need an automated system that maintains a “human-like” conversation quality, is auditable, and complies with local regulations (privacy, consent, telemarketing).

Consider the critical issues known to date that must be mitigated by the solution:
* **Regulations**: You must be very strict about consent, opt-in, time limits, and exclusion list management (e.g., no spam, no political calls without permission, etc.).
* **Quality of prompt design**: The agent must be persuasive but not aggressive, always respecting the "no" response and providing clear information about who it represents.
* **Latency & resilience**: Audio streaming + real-time LLM must be well-designed, especially in the custom scenario - target < 800ms - 1.5sec;
* **Observability/eval**: You will need logs and metrics to *truly* monitor how the agent behaves, also for compliance reasons.

### Target Users & Context

* **Client organizations**: research institutes, enterprises, public entities running structured surveys (customer satisfaction, market research, etc.).
* **End user**: the person receiving the call who must:

  * understand who is calling and why,
  * decide whether to opt in,
  * answer 3 questions (free text or guided choices).
* **Technical context**:

  * cloud or on-prem backend,
  * integration with one or more LLMs (GPT, Claude, Gemini) via a gateway,
  * telephony providers via APIs (Twilio/Vonage/Plivo/Telnyx) or voice AI platforms (Bland AI, Vapi, Retell).

### Value & Expected Outcomes

* Scale from tens to thousands of calls per day, across countries and languages.
* Standardize tone of voice, script, and consent handling.
* Lower cost per completed interview.
* Full traceability: each call has an outcome, conversation log, and survey result.
* Ability to experiment with different “agent personalities” (formal/informal, etc.) without changing the core infrastructure.

---

### Core Functional Flows

#### 1. Campaign setup and call scheduling

* Import a contact list (phone number, email, preferred language, existing consent flags).
* Define the survey:

  * opening/intro script,
  * 3 questions: 1) Request for personal details (First Name, Surname, Age, Residence, Tax Code; 2) Favorite Places; 3) Favorite Restaurants
  * Any minimum branching rules (e.g., if it rejects, what
  * minimal branching rules (e.g., if user declines, end immediately).
* Configure time windows and max retry attempts (e.g., 5 per contact).

#### 2. Call where user answers **and** accepts the survey

1. The agent places the call.
2. When the person answers, the LLM-driven agent:

   * introduces itself (identity, purpose, expected duration);
   * explicitly asks for consent to proceed.
3. If the person agrees, the agent asks the 3 questions and records the answers.
4. Once finished, the system:

   * closes the call with a “thank you”;
   * publishes a `survey.completed` event to a queue with contact ID, answers, timestamp;
   * a worker consumes the event and sends a pre-defined email to the respondent (thanks, information notice, reward link, etc.).
5. The contact’s state becomes **“Completed”** (no more attempts).

#### 3. Call with **no answer** or **busy**

* If the call is not answered or the line is busy:

  * log the attempt outcome (no answer/busy);
  * push the contact back into a **retry queue** with an incremented attempt counter;
  * a scheduler re-plans the call for a later time within allowed time windows.
* After the maximum number of attempts (e.g., 5) is reached:

  * the contact’s state becomes “Not reachable”;
  * optionally, an informational email can be sent (e.g., “we tried to reach you for a survey, here is a link if you’d like to participate”), also driven by a queue (e.g., `survey.not_reached`).

#### 4. Call where user refuses / cannot be convinced

* If the person refuses or explicitly says they do not want to participate:

  * the agent closes politely;
  * the contact’s state becomes “Refused”;
  * a `survey.refused` event is published, and if the process requires it,

    * a short email can be sent (e.g., thanking them and confirming they will not be contacted again).

---

### Telephony integration modes

The agent must support two alternative, configurable integration modes.

#### Mode A – **Custom LLM integration + Voice API provider (e.g., Twilio, etc.)**

* Use “traditional” voice API providers:

  * **Twilio Programmable Voice** for inbound/outbound calls and IVR/survey scenarios.([Twilio][1])
  * **Vonage Voice API** to create and control outbound calls.([developer.vonage.com][2])
  * **Plivo Voice API** for outbound and bulk calling.([plivo.com][3])
  * **Telnyx Programmable Voice** for voice calling plus AI-oriented workflows (media streaming, etc.).([developers.telnyx.com][4])
* Our gateway orchestrates:

  * streaming speech-to-text,
  * calls to the generative model (GPT/Claude/Gemini),
  * streaming text-to-speech,
  * survey state management.
* Pros: full flexibility and control (model choice, routing, data residency).
* Cons: higher engineering complexity (media streaming, latency, scaling).

#### Mode B – **Voice AI platforms (Bland AI / Vapi / Retell)**

* Leverage specialized voice AI platforms:

  * **Bland AI** – enterprise-grade voice agents for inbound/outbound calls (sales, surveys, scheduling).([bland.ai][8])
  * **Vapi** – developer platform for voice AI agents, with phone-call support and highly configurable APIs.([Vapi][6])
  * **Retell AI** – API-first voice agent platform supporting inbound/outbound calls and multiple telephony providers.([retellai.com][7])
* In this scenario:

  * the platform handles telephony and often STT/TTS itself;
  * we focus on:

    * scripting the agent’s personality and behavior,
    * integrating with our backend via webhooks to:

      * store survey answers,
      * receive call outcomes,
      * trigger email and queue events.
* Pros: much faster time-to-market; audio, latency, and concurrency are largely solved.
* Cons: vendor lock-in, less low-level control, potential constraints on model choice and data residency.

**Configuration requirement:**

* An environment-level flag (e.g., `VOICE_PROVIDER_MODE = "custom" | "bland" | "vapi" | "retell"`) selects which adapter to use at runtime, with a stable domain-level interface for campaigns and call outcomes.

---

### Non-functional requirements

* **Low conversational latency** (target < 1–2 seconds round-trip) to avoid “robotic pauses”.
* **Multi-language support**, starting from English/Italian.
* **Compliance & privacy**:

  * respect for local regulations (GDPR, telemarketing rules, opt-in/out, time windows);
  * controlled logging and retention for call recordings and transcripts.
* **Scalability**: thousands of calls per day, with control over:

  * call rate,
  * max concurrent calls,
  * multi-provider routing.
* **Observability**: dashboards and metrics (answer rate, completion rate, refusal rate, costs).

---

### Short vendor list

**Telephony / Voice API providers**

* Twilio Programmable Voice.([Twilio][1])
* Vonage Voice API.([developer.vonage.com][2])
* Plivo Voice API.([plivo.com][3])
* Telnyx Voice API.([developers.telnyx.com][4])

**Voice AI agent platforms**

* Bland AI.([bland.ai][8])
* Vapi.([Vapi][6])
* Retell AI.([retellai.com][7])

---


[1]: https://www.twilio.com/docs/voice?utm_source=chatgpt.com "Programmable Voice"
[2]: https://developer.vonage.com/en/api/voice?utm_source=chatgpt.com "Vonage Voice API Reference"
[3]: https://www.plivo.com/docs/voice/api/call/make-a-call?utm_source=chatgpt.com "Make an outbound call"
[4]: https://developers.telnyx.com/docs/voice/programmable-voice/get-started?utm_source=chatgpt.com "Getting Started with Telnyx Programmable Voice API"
[5]: https://www.bland.ai/?utm_source=chatgpt.com "Bland AI | Automate Phone Calls with Conversational AI for ..."
[6]: https://vapi.ai/?utm_source=chatgpt.com "Vapi - Build Advanced Voice AI Agents"
[7]: https://www.retellai.com/?utm_source=chatgpt.com "AI Voice Agent Platform for Phone Call Automation"
[8]: https://www.bland.ai/voice-agent?utm_source=chatgpt.com "Voice Agent That Sounds Human"
[9]: https://www.retellai.com/glossary/ai-voice-agent?utm_source=chatgpt.com "AI Voice Agent"
