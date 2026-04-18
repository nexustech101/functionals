## Possible Feature Implemnetations & Architectural Decisions

### Tree Data Structures

- Use recursive trees for efficient storage/access to data
  - Binary search tree
  - Recursive tree for data that is similar in *shape* (Like  B-tree)
  - Graphs for representing relationships
- Use graphs for complex relationships between objects
- What if I wanted to store data as a graph, or have support for a vectore database?
  - search filtering or similarity search
  - model memory storage
  - social network graph
  - add features to `functionals.db` to support graph and network data. **(high priority)**
- Knowledge graph for LLMs

### Other Agent Features

- Pruning model memory/context window
- Data compression
- Context summary (summarize high level objects and structures of high priority)
  - how can we *prioritize* things? how should we define priority?

### Questions

- How do LLMs manage memory?
- How do LLMs store and retrieve data? Is there a *better* way of doing so?
- What is the lifecycle of an AI workflow/chat?
- Why do LLMs run out of context window size?
- Is it possible to store a highly compressed representation of model context?
  - can we preserve speed of access?
  - what is the efficiency-gains threshhold to justify the implementation?
- Can I use NLP or RNN networks for building reliable relationship graphs between objects? For instance, if an agent has a working history of a project, how can we represent the working tree? Should we have multiple layers of representation/abstraction? What can we gain from this?
  - fast traversal of information
  - how should we represent the worktree and how can we take advantage of that structure
  - how does git implement their worktree?
- What software architecture would be useful for AI self-improvement? Can we write an algorithm that let's an agent iterate and optimize? Can we define a suite of statistical algorithms for the agents to use? Should this be an mcp service?
  - I need to build an algorithm for applying the scientific method. It should be designed such that the algorithm can adapt and optimize for *high-impact sampling* strategies (RL, RNN?)
- Models typically like to remember output from verbose commands; is there a way to reliably prune that from context at runtime, or before next prompt cycle? That would be useful.

### FX Features

- Create more commands for the fx manager
  - **run**: runs the application
  - **install**: installs the pyproject to python packages (install -e)
  - **update**: updates decorates package to latest version without deleting cache data (db, configs, etc.)
  - **pull**: pulls plugins from a git repo containing plugin structure
  - **worktree**: prints worktree of fx project (stored in .fx, similar to how git does it, but more efficiently)
- Developers should have the option to use uv for managing their project and python environment.

How should I abstract architectural specs from feature specs? I need to define the optimal architecture to use for a particular feature, then define the specs for implementing the feature.

Archictecture surface spec and feature spec? This just helps me with my workflow; this doesn't provide any functional gains.