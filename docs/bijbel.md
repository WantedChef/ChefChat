<chefchat_master_specification version="2.0">
    <metadata>
        <project_name>ChefChat: The Michelin Star AI-Engineer</project_name>
        <vision>Transform CLI into a High-Performance Culinary Dashboard (TUI) with Swarm Intelligence.</vision>
        <core_metaphor>The Professional Kitchen (User=Head Chef, AI=Brigade, Code=Dish).</core_metaphor>
        <status>APPROVED_FOR_CONSTRUCTION</status>
        <language>Python 3.11+</language>
    </metadata>

    <analysis_report>
        <executive_summary>
            Het concept is visionair en technisch haalbaar. De combinatie van 'Textual' voor de TUI
            en een 'Actor Model' voor de AI-agents lost het probleem van 'CLI-vermoeidheid' en 'AI-latentie' op.
            De grootste technische uitdaging ligt in de 'State Synchronization' tussen de asynchrone agents
            en de UI-thread.
        </executive_summary>

        <structural_check>
            <component name="TUI (Textual)" status="OPTIMAL">
                <validation>Het 3-panel layout (Ticket, Pass, Plate) is perfect voor `textual.containers.Grid`. Reactive updates zijn essentieel.</validation>
                <risk>Performance impact bij veel log-updates in 'The Pass'. Oplossing: Batch updates / Debouncing.</risk>
            </component>
            <component name="Swarm Architecture" status="COMPLEX">
                <validation>Actor Model is de juiste keuze. Python's `asyncio` is vereist. Parallelisme verhoogt snelheid.</validation>
                <recommendation>Implementeer een centrale `EventBus` (Pub/Sub) waar Agents op abonneren, ontkoppeld van de UI.</recommendation>
            </component>
            <component name="Knowledge Graph" status="CRITICAL">
                <validation>AST-parsing is superieur aan regex/tekst-zoeken. Maakt 'ChefChat' uniek.</validation>
                <library_choice>Gebruik `tree-sitter` of Python's native `ast` module + `networkx` voor de graph.</library_choice>
            </component>
        </structural_check>

        <security_audit>
            <vulnerability id="SEC-01" severity="CRITICAL">
                <name>Arbitrary Code Execution (RCE)</name>
                <description>De 'Line Cook' genereert en voert code uit.</description>
                <mitigation>
                    1. Code uitvoering (Pytest) MOET in een geïsoleerde omgeving (Docker Container / Sandbox).
                    2. Implementeer `AST Guardrails` om gevaarlijke imports (`os`, `subprocess`) te blokkeren voor uitvoering.
                </mitigation>
            </vulnerability>
            <vulnerability id="SEC-02" severity="HIGH">
                <name>Supply Chain Poisoning</name>
                <description>AI suggereert hallucinerende of kwaadaardige packages.</description>
                <mitigation>De 'Sommelier' agent moet package-bestaan verifiëren via PyPI API vóór installatie.</mitigation>
            </vulnerability>
        </security_audit>

        <ux_review>
            <aesthetic>Dark Kitchen (Slate & Saffron) is uitstekend voor contrast en focus.</aesthetic>
            <consistency>De termen (Mise en place, Ticket, Plate) moeten strikt worden doorgevoerd in error messages en logs.</consistency>
            <feature_refinement>
                <suggestion>Verander "Plongeur" naar "Expeditor" voor QA-taken. Plongeur is beter voor garbage collection/cache clearing.</suggestion>
            </feature_refinement>
        </ux_review>
    </analysis_report>

    <tech_stack>
        <core>
            <ui_framework>Textual (built on Rich)</ui_framework>
            <async_engine>Python asyncio</async_engine>
            <data_validation>Pydantic (voor Message Protocol & Recipe Schema)</data_validation>
            <graph_db>NetworkX (in-memory) of Neo4j (optioneel, later)</graph_db>
        </core>
        <file_structure>
            <root>
                <dir name="chefchat">
                    <dir name="kitchen">
                        <file>brigade.py (Actor Manager)</file>
                        <file>bus.py (Event Loop)</file>
                        <dir name="stations">
                            <file>sous_chef.py</file>
                            <file>line_cook.py</file>
                            <file>sommelier.py</file>
                        </dir>
                    </dir>
                    <dir name="interface">
                        <file>tui.py (Textual App)</file>
                        <file>styles.tcss</file>
                        <dir name="widgets">
                            <file>ticket_rail.py</file>
                            <file>the_pass.py</file>
                            <file>the_plate.py</file>
                        </dir>
                    </dir>
                    <dir name="pantry">
                        <file>recipes.py (YAML Parsers)</file>
                        <file>ingredients.py (Knowledge Graph)</file>
                    </dir>
                </dir>
            </root>
        </file_structure>
    </tech_stack>

    <implementation_strategy>
        <instruction>
            Hieronder staan de specifieke prompts om de code te genereren.
            Kopieer deze prompts één voor één naar uw AI-coding assistant (of naar mij) om het project te bouwen.
        </instruction>

        <prompt_template id="step_1_scaffolding">
            <role>Senior Python Architect</role>
            <task>
                Zet de projectstructuur op voor 'ChefChat' gebaseerd op de XML-specificatie.
                1. Maak de mappenstructuur aan (`chefchat/kitchen`, `chefchat/interface`, etc.).
                2. Maak een `poetry` of `pip` `pyproject.toml` bestand met dependencies: `textual`, `rich`, `pydantic`, `networkx`, `openai` (of andere LLM lib).
                3. Maak het bestand `chefchat/interface/styles.tcss` met de CSS variabelen voor het kleurenpalet:
                   - Primary-bg: #1a1b26
                   - Panel-border: #414868
                   - Accent: #e0af68
                   - Success: #9ece6a
                   - Error: #f7768e
            </task>
        </prompt_template>

        <prompt_template id="step_2_tui_layout">
            <role>Frontend Engineer (Textual Specialist)</role>
            <task>
                Implementeer `chefchat/interface/tui.py` en de widgets.
                1. Maak een `ChefChatApp(App)` klasse.
                2. Implementeer de 3-pane layout met `CSS Grid` of `Vertical/Horizontal` containers.
                   - Pane 1: "The Ticket" (Links boven) - Scrollable text area voor chat historie.
                   - Pane 2: "The Pass" (Rechts boven) - Lijst met `ProgressBar` widgets per Agent.
                   - Pane 3: "The Plate" (Onder) - Syntax highlighted code view (Rich Syntax).
                3. Voeg de "Whisk" loader animatie toe (ASCII art spinner).
                4. Zorg dat de UI start en eruit ziet als de "Dark Kitchen" specificatie.
            </task>
        </prompt_template>

        <prompt_template id="step_3_async_bus">
            <role>Backend Systems Engineer</role>
            <task>
                Implementeer het asynchrone brein in `chefchat/kitchen/bus.py`.
                1. Definieer een Pydantic model `ChefMessage`:
                   - `sender`: str (Station Name)
                   - `recipient`: str (Station Name or 'ALL')
                   - `payload`: dict
                   - `priority`: int
                2. Schrijf een `KitchenBus` klasse met `asyncio.Queue`.
                3. Maak een abstracte `BaseStation` klasse waar alle agents (Sous-Chef, etc.) van erven.
                   - Elke station heeft een `listen()` loop die berichten van de bus pakt.
            </task>
        </prompt_template>
    </implementation_strategy>

</chefchat_master_specification>
