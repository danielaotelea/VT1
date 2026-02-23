# What is an AI Agent?

An AI agent is a piece of software that use AI to complete a task of behalf of users.
As a **"Digital Brain"** with 3 peripheral components:

* Memory <Context> : Stores past interactions, knowledge, and context to inform future decisions.
* Planning <Execution> : to break the task into smaller steps
* Tools <Interaction> : to interact with the external world, such as APIs, databases, or other software systems.

it can learn, adapt and have different levels of autonomy.

--- 

## ReAct - The internal Reasoning Loop

[The ReAct pattern](https://arxiv.org/abs/2210.03629) describes how an agent operates in an **iterative loop of thought
**, **action**, and **observation** until an exit condition is met.

* **Thought**: The model reasons about the task and it decides what to do next. The model evaluates all of the
  information that it's gathered in order to determine whether the user's request has been fully answered.

* **Action**: Based on its thought process, the model takes one of two actions:
    * If the task isn't complete, it selects a tool and then it forms a query to gather more information.
    * If the task is complete, it formulates the final answer to send to the user, which ends the loop.

* **Observation**: The model receives the output from the tool and it saves relevant information in its memory. Because
  the model saves relevant output, it can build on previous observations, which helps to prevent the model from
  repeating itself or losing context.

![image](img/react.svg)

```mermaid
%%{init: {'securityLevel': 'loose', 'htmlLabels': false}}%%
graph TD
    Start((Start: Goal Defined)) --> Thought

    subgraph ReAct_Loop [Reasoning & Execution Loop]
        Thought["**Thought**<br/>Internal Reasoning:<br/>'What tool do I need?'"] --> Action
        
        Action["**Action**<br/>Generate Tool Call<br/>(e.g., search_web, run_code)"] --> ToolEnv
        
        subgraph External_World [Tool Integration Layer]
            ToolEnv["**Tools/APIs**<br/>External execution of<br/>the requested action"]
        end

        ToolEnv --> Observation
        
        Observation["**Observation**<br/>Capture Tool Output<br/>& update Context/Memory"]
    end

    Observation --> Check{Goal Reached?}
    Check -- No --> Thought
    Check -- Yes --> End((End: Task Complete))

    %% Styling
    style ReAct_Loop fill:#f9f9f,stroke:#333,stroke-dasharray: 5 5
    style External_World fill:#fff4d,stroke:#d4a017,stroke-width:2px
    style Thought fill:#e1f5f,stroke:#01579b
    style Action fill:#e8f5e,stroke:#2e7d32
    style Observation fill:#fff3e,stroke:#ef6c00
    style ToolEnv fill:#f3e5f,stroke:#7b1fa2,stroke-width:2px
```

----

## Deterministic Workflow vs. Dynamic Orchestration

* Deterministic Workflow: A fixed sequence of steps that the agent follows to complete a task. This approach is
  straightforward and easier to debug but may not be flexible enough for complex or unpredictable tasks.
```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 
  'primaryColor': '#e1f5fe', 
  'edgeLabelBackground': '#9e9e9e',
  'linkColor': '#ffffff',
  'linkColor2': '#ffffff',
  'arrowheadColor': '#ffffff',
  'lineColor': '#ffffff',
  'edgeStroke': '#ffffff',
  'primaryTextColor': '#ffffff',
  'edgeLabelBackgroundOut': '#9e9e9e',
  'edgeLabelBackgroundIn': '#9e9e9e'
}}}%%
graph LR
    Start((Start)) --> Step1[Step 1: Input Validation & Processing]
    Step1 --> Step2[Step 2: Tool Execution]
    
    Step2 --> RetryCount{Retry Attempts<br/>≤ 3?}
    
    RetryCount -->|Yes| Condition{Validation<br/>Passed?}
    RetryCount -->|No| Escalate[Escalate to Human<br/>or Alert System]
    
    Condition -->|✓ Success| Step3[Step 3: Output Formatting & Logging]
    Condition -->|✗ Fail| Error[Error Logging<br/>Backoff Delay]
    
    Error --> Step2
    
    Step3 --> Metrics[Metrics & Audit Log]
    Metrics --> End((End: Output))
    Escalate --> End2((Escalate/Abort))

    style Start fill:#000000,stroke:#333,stroke-width:3px,color:#ffffff
    style End fill:#000000,stroke:#333,stroke-width:3px,color:#ffffff
    style End2 fill:#000000,stroke:#ff9800,stroke-width:3px,color:#ffffff
    style Condition fill:#000000,stroke:#fbc02d,stroke-width:3px,color:#ffffff
    style RetryCount fill:#000000,stroke:#fbc02d,stroke-width:3px,color:#ffffff
    style Step1 fill:#000000,stroke:#1e88e5,stroke-width:3px,color:#ffffff
    style Step2 fill:#000000,stroke:#1e88e5,stroke-width:3px,color:#ffffff
    style Step3 fill:#000000,stroke:#1e88e5,stroke-width:3px,color:#ffffff
    style Error fill:#000000,stroke:#e53935,stroke-width:3px,color:#ffffff
    style Metrics fill:#000000,stroke:#4caf50,stroke-width:3px,color:#ffffff
    style Escalate fill:#000000,stroke:#ff9800,stroke-width:3px,color:#ffffff
```

* Dynamic Orchestration: The agent dynamically decides which steps to take based on the current context and information.
  This allows for greater flexibility and adaptability but can be more challenging to design and debug.
```mermaid
graph TD
    A[Start Task] --> B[Observe Context]
    B --> C{Evaluate State}
    C -->|Need Info| D[Call Tool/Action 1]
    D --> E[Get Observation]
    E --> B
    C -->|Need Info| F[Call Tool/Action 2]
    F --> G[Get Observation]
    G --> B
    C -->|Need Info| H[Delegate to Sub-Agent]
    H --> I[Sub-Agent Response]
    I --> B
    C -->|Done| J[Output Final Answer]
    J --> K[End]
    
    classDef decision fill:#fff9e,stroke:#ffcc66,stroke-width:2px
    classDef action fill:#f0f8f,stroke:#3399ff,stroke-width:2px
    class C decision
    class D,F,H action
```

## Multi-Agent Coordination

When tasks are too complex, some coordination patterns are used to manage multiple agents working together:

* **The Coordinator Pattern (Dynamic)**: A central agent (the Orchestrator) acts as the router. It receives the user's
  goal, breaks it down, and assigns sub-tasks to specialized worker agents (e.g., a "Researcher Agent" and a "Coder
  Agent").
* **Sequential/Parallel Workflows**: Used when the steps are predictable. Information flows linearly from one agent to
  the next, or multiple agents work on the same problem at once to compare results.
* **Iterative Refinement**: An "Actor Agent" produces a draft, and a "Reviewer Agent" provides feedback, looping until
  the goal is met.

[Reference: Google Cloud: Design Patterns for Agentic AI](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system#workflows-that-require-dynamic-orchestration)
