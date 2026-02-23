# What is an AI Agent?

An AI agent is a piece of software that use AI to complete a task of behalf of users.
As a **"Digital Brain"** with 3 peripheral components:

* Memory <Context> : Stores past interactions, knowledge, and context to inform future decisions.
* Planning <Execution> : to break the task into smaller steps
* Tools <Interaction> : to interact with the external world, such as APIs, databases, or other software systems.

it can learn, adapt and have different levels of autonomy.

--- 
## ReAct - The internal Reasoning Loop 

[The ReAct pattern](https://arxiv.org/abs/2210.03629) describes how an agent operates in an **iterative loop of thought**, **action**, and **observation** until an exit condition is met.

* **Thought**: The model reasons about the task and it decides what to do next. The model evaluates all of the information that it's gathered in order to determine whether the user's request has been fully answered.

* **Action**: Based on its thought process, the model takes one of two actions:
    * If the task isn't complete, it selects a tool and then it forms a query to gather more information.
    * If the task is complete, it formulates the final answer to send to the user, which ends the loop.

* **Observation**: The model receives the output from the tool and it saves relevant information in its memory. Because the model saves relevant output, it can build on previous observations, which helps to prevent the model from repeating itself or losing context.



![image](img/react.svg)


```mermaid
%%{init: {'securityLevel': 'loose', 'htmlLabels': false}}%%
graph TD
    Start((Start: Goal Defined)) --> Thought
    
    subgraph ReAct_Loop [Continuous Planning Cycle]
        Thought["Thought\nReason about optimal path\nOptimize for Time/Energy"] --> Action
        Action["Action\nExecute movement along\ncalculated path segment"] --> Observation
        Observation["Observation\nCapture and save new state\nand environment changes"]
    end

    Observation --> Check{Goal Reached?}
    Check -- No --> Thought
    Check -- Yes --> End((End: Task Complete))

    style ReAct_Loop fill:#fffff,stroke:#33,stroke-dasharray:5 5
    style Thought fill:#ddde7ff,stroke:#004a99
    style Action fill:#dedda,stroke:#155724
    style Observation fill:#fffcd,stroke:#856404
```
----
