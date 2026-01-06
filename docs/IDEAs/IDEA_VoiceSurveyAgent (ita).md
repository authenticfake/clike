## 1. Formalizzazione 

### Titolo

**Voice Survey Agent** – Agente vocale AI per sondaggi telefonici nazionali e internazionali

### Visione

Realizzare un agente vocale AI in grado di effettuare chiamate telefoniche nazionali e internazionali, parlare in linguaggio naturale con le persone e convincerle, in modo trasparente e non aggressivo, a partecipare a un breve sondaggio di 3 domande. L’agente deve integrarsi con modelli generativi (GPT, Claude, Gemini) e con provider telefonici, gestendo automaticamente esiti, retry e invio di e-mail di follow-up.

### Problema da risolvere

Oggi i sondaggi telefonici richiedono operatori umani, con costi elevati, risultati poco scalabili e qualità non uniforme del dialogo. Inoltre è complesso orchestrare:

* tentativi di chiamata ripetuti,
* gestione di occupato/non risposta,
* invio di e-mail di conferma o chiusura,
* raccolta strutturata delle risposte.

Serve un sistema automatizzato che mantenga una qualità di conversazione “umana”, tracciabile e conforme alle normative locali (privacy, consenso, telemarketing).

Considera le criticità ad oggi conosciute che devono essere mitigate dalla soluzione:
* **Normative**: devi essere molto rigoroso su consenso, opt-in, limiti orari e gestione delle liste di esclusione (es. no spam, no chiamate politiche senza permesso, ecc.).
* **Qualità del prompt design**: l’agente deve essere persuasivo ma non aggressivo, rispettando sempre il “no” e dando informazioni chiare su chi rappresenta.
* **Latenza & resilienza**: streaming audio + LLM real-time vanno progettati bene, soprattutto sullo  scenario custom - target < 800ms - 1.5sec;
* **Osservabilità/eval**: ti serviranno log e metriche per controllare *davvero* come l’agente si comporta, anche per motivi di compliance.

### Target utenti & contesto d’uso

* **Committenza**: istituti di ricerca, aziende, enti pubblici che vogliono condurre sondaggi strutturati (es. customer satisfaction, ricerche di mercato).
* **Utente finale**: persona contattata telefonicamente (privato cittadino o cliente) che deve:

  * capire chi la sta chiamando e perché,
  * decidere se partecipare,
  * rispondere a 3 domande a risposta libera o guidata.
* **Contesto tecnologico**:

  * backend cloud o on-prem,
  * integrazione con uno o più modelli LLM (GPT, Claude, Gemini) via gateway,
  * provider telefonici via API (Twilio/Vonage/Plivo/Telnyx, oppure piattaforme voice AI come Bland AI, Vapi, Retell).

### Valore & risultati attesi

* Scalare da poche decine a migliaia di chiamate al giorno, anche in più paesi e lingue.
* Standardizzare il tono di voce, lo script e il rispetto del consenso.
* Ridurre il costo per intervista completata.
* Avere tracciabilità completa: ogni chiamata ha esito, log conversazionale, risultati del sondaggio.
* Possibilità di sperimentare diversi “stili” di agente (più formale/informale) senza cambiare l’infrastruttura.

---

### Flussi funzionali principali

#### 1. Avvio campagna e scheduling chiamate

* Import di una lista di contatti (numero, e-mail, lingua preferita, eventuali consensi già raccolti).
* Definizione del sondaggio:

  * testo di apertura/introduzione,
  * 3 domande: 1) Richiesta delle generalita (Nome Cognome, eta, Residenza, Codice FIscale; 2) Locali Preferiti; 3) Ristoranti Preferiti 
  * eventuali regole di branching minimo (es. se rifiuta, chiudi subito).
* Pianificazione fascia oraria e numero massimo di tentativi (es. max 5 per contatto).

#### 2. Chiamata con esito “risponde + accetta il sondaggio”

1. L’agente effettua la chiamata.
2. Quando la persona risponde, l’LLM:

   * si presenta (identità, mandato, durata del sondaggio);
   * chiede esplicitamente il consenso a procedere.
3. Se la persona accetta, l’agente pone le 3 domande e registra le risposte.
4. A sondaggio concluso, il sistema:

   * chiude la chiamata con un ringraziamento;
   * pubblica un evento su una coda (es. `survey.completed`) con: ID contatto, risposte, timestamp;
   * un worker legge la coda e invia l’e-mail con testo predefinito al rispondente (es. ringraziamento, eventuale link informativa, reward, ecc.).
5. Lo stato del contatto passa a **“Completato”** (niente ulteriori tentativi).

#### 3. Chiamata con **non risposta** o **occupato**

* Se il numero non risponde o risulta occupato:

  * lo stato per quel tentativo viene tracciato (no answer/busy);
  * il contatto viene rimesso in una **coda di retry** con un contatore di tentativi;
  * un job di scheduling riprogramma la chiamata in una finestra successiva (rispettando fasce orarie consentite).
* Dopo un massimo di 5 tentativi falliti:

  * lo stato passa a “Non raggiungibile”;
  * opzionale: invio di e-mail di informazione (es. “abbiamo provato a contattarti per un sondaggio, se vuoi partecipare clicca qui”), anch’essa orchestrata tramite una coda (es. `survey.not_reached`).

#### 4. Chiamata con rifiuto / impossibile convincerlo

* Se la persona rifiuta subito o, nonostante il tentativo di spiegazione, conferma di non voler partecipare:

  * l’agente chiude in modo cortese;
  * lo stato passa a “Rifiutato”;
  * viene pubblicato un evento (es. `survey.refused`) e – se previsto dal processo –

    * può partire un’e-mail di ringraziamento/comunicazione (es. conferma che non verrà ricontattato).

---

### Modalità di integrazione con il provider telefonico

L’agent deve supportare due modalità alternative e configurabili.

#### Modalità A – **Custom LLM + provider VoIP (es. Twilio & simili)**

* Utilizzo di provider “classici” di Voice API per telefonia:

  * **Twilio Programmable Voice** per chiamate inbound/outbound e IVR/sondaggi vocali.([Twilio][1])
  * **Vonage Voice API** per creare e controllare chiamate outbound.([developer.vonage.com][2])
  * **Plivo Voice API** per chiamate outbound anche in bulk.([plivo.com][3])
  * **Telnyx Programmable Voice** per integrare chiamate e flussi AI (media streaming, ecc.).([developers.telnyx.com][4])
* L’LLM (GPT/Claude/Gemini) è orchestrato da un nostro gateway che gestisce:

  * speech-to-text in streaming,
  * chiamate al modello generativo,
  * text-to-speech in tempo reale,
  * logica di stato del sondaggio.
* Pro: massima flessibilità tecnologica e controllo di:

  * scelta modello,
  * politiche di routing,
  * compliance (es. dove risiedono i dati).
* Contro: maggiore complessità di implementazione (media streaming, low-latency, scaling).

#### Modalità B – **Voice AI platform (Bland AI / Vapi / Retell)**

* Uso di piattaforme specializzate in agenti vocali AI:

  * **Bland AI**: piattaforma per automatizzare chiamate inbound/outbound, con voice agents per reminder, sondaggi, lead qualification.([bland.ai][5])
  * **Vapi**: piattaforma per sviluppatori per creare voice agents che fanno e ricevono telefonate, con API molto configurabile.([Vapi][6])
  * **Retell AI**: piattaforma API-first per voice agent in produzione, con supporto inbound/outbound e integrazione con provider telefonici, monitoring e tooling.([retellai.com][7])
* In questo scenario:

  * la piattaforma gestisce nativamente la parte telefonica e spesso anche STT/TTS;
  * noi ci concentriamo su:

    * definizione dello script/“personalità” dell’agente,
    * integrazione con il nostro backend (webhook) per:

      * registrare le risposte,
      * ricevere gli esiti delle chiamate,
      * attivare e-mail e code di dominio.
* Pro: time-to-market rapido, gestione semplificata di audio, latenza, concurrency.
* Contro: lock-in verso la piattaforma, meno controllo di basso livello, possibili limiti su scelta LLM o regioni.

**Configurazione desiderata:**

* Un parametro di configurazione a livello di ambiente/progetto (es. `VOICE_PROVIDER_MODE = "custom" | "bland" | "vapi" | "retell"`) che seleziona a runtime quale integrazione usare, lasciando invariata l’interfaccia verso il dominio (stesso “contratto” per avviare campagne, ricevere esiti, ecc.).

---

### Requisiti non funzionali chiave

* **Latenza conversazionale** bassa (target < 800ms–1.5 secondo round-trip) per non dare la sensazione di “bot lento”.
* **Multilingua** (almeno inglese/italiano, estensibile ad altre lingue dei modelli LLM e TTS).
* **Compliance & privacy**:

  * rispetto delle normative locali (GDPR, regole su telemarketing, consenso esplicito, liste di opt-out, limiti orari);
  * logging e retention controllata delle registrazioni vocali e trascrizioni.
* **Scalabilità**: supporto a campagne con migliaia di contatti, con controllo di:

  * rate limit di chiamata,
  * concorrenza massima di chiamate attive,
  * bilanciamento sui provider.
* **Osservabilità**: dashboard per metriche chiave (tasso di risposta, tasso di completamento, rifiuti, costi).

---

### Lista sintetica di fornitori rilevanti

**Telephony / Voice API “classiche”**

* Twilio Programmable Voice (globale, robusto su IVR e survey).([Twilio][1])
* Vonage Voice API (ex Nexmo, forte su copertura internazionale).([developer.vonage.com][2])
* Plivo Voice API (outbound, bulk calling, pricing competitivo).([plivo.com][3])
* Telnyx Voice API (programmable voice + focus su AI assistants/media streaming).([developers.telnyx.com][4])

**Piattaforme Voice AI / Agent**

* Bland AI – AI voice agents per outbound massivo (sales, survey, scheduling).([bland.ai][8])
* Vapi – developer platform per voice AI agents, API molto configurabile.([Vapi][6])
* Retell AI – voice agent platform API-first, con supporto inbound/outbound e integrazione telephony.([retellai.com][7])

---

### Fattibilità – cosa ne penso

**È fattibile e già in trend di mercato.**

* Lato telephony, tutti i provider citati supportano chiamate outbound programmatiche per scenari tipo IVR e survey.([Twilio][1])
* Lato AI, la combinazione di STT/TTS in streaming + LLM (GPT, Claude, Gemini) è ormai stabile e usata in produzione da diverse piattaforme.([retellai.com][9])

**Le criticità vere:**

* **Normative**: devi essere molto rigoroso su consenso, opt-in, limiti orari e gestione delle liste di esclusione (es. no spam, no chiamate politiche senza permesso, ecc.).
* **Qualità del prompt design**: l’agente deve essere persuasivo ma non aggressivo, rispettando sempre il “no” e dando informazioni chiare su chi rappresenta.
* **Latenza & resilienza**: streaming audio + LLM real-time vanno progettati bene, soprattutto se resti nello scenario custom; le piattaforme “voice AI” nascono proprio per risolvere questo.
* **Osservabilità/eval**: ti serviranno log e metriche per controllare *davvero* come l’agente si comporta, anche per motivi di compliance.


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
