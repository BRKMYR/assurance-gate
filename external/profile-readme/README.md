# Product Manager · Spatial Intelligence · Safe Autonomy · Physical AI

### Product strategist and builder in B2B deep tech: AI & data platforms for autonomous vehicles, Physical and Industrial AI.

Close to a decade in product management. On this GitHub I explore the latest market and technology trends and turn them into AI project prototypes. Everything here is personal work, built fully outside of and unrelated to my employment. I build at the intersection of spatial intelligence, autonomous systems and AI safety, with a focus on **Operational Design Domain (ODD) management**: deciding where an automated driving function is cleared to operate and where it must hand back, by road, region and condition, so that agents perceive, reason, and act only where they are cleared to.

Data engines, evals, and RL environments: the data loop behind AD/ADAS, dual use Earth Observation, and industrial automation. Several of the projects below are in **stealth mode**: they live in private repositories until they are ready to ship. Public repos are linked where available.

My background in Physical AI goes back to 2016, when I worked with the **iCub humanoid robot** at TU Munich. The work covered visual recognition, semantic reasoning, and visual servoing. It combined CNNs with structured knowledge so a robot could recognize objects it had never seen. That early work on grounding perception in reasoning shapes how I approach autonomous product development today. See [`icub-visual-recognition`](https://github.com/BRKMYR/icub-visual-recognition), [`icub-semantic-reasoning`](https://github.com/BRKMYR/icub-semantic-reasoning), [`icub-visual-servoing`](https://github.com/BRKMYR/icub-visual-servoing).

---

## Focus Areas

### Safe Autonomy: Assurance, Evals and ODD
ODD management as a clearance question: where an automated driving function may operate, where it must hand back, and how that boundary is maintained in the map rather than discovered in test. Alongside it, safety evaluation for autonomous driving with adversarial scenarios and safety critical metrics on a vendor neutral scorecard, applying **UL 4600** and **SOTIF** (ISO 21448). Real time safety monitoring for robotaxi fleets with teleoperation trigger detection on Waymax and the Waymo Open Motion Dataset. Adversarial robustness tooling is public: [`pytorch-shield`](https://github.com/BRKMYR/pytorch-shield). Above the benchmarks sits the decision layer, where thresholds exist before the data and every claim carries its evidence.

### Spatial Intelligence: SAR and Earth Observation
SAR and EO AI pipelines from satellite tasking to intelligence product: Sentinel-1 acquisition, change and ship detection, damage assessment, and a vision language analyst console that refuses questions the imaging physics cannot answer. In stealth.

### World Models and Synthetic Data
World foundation model evaluation for the sim to real gap: six metrics, six failure modes, closed form baselines so the harness itself can be validated. Domain randomized synthetic data for long tail edge cases. In stealth.

### Agentic AI and Human Machine Teaming
Multi agent reinforcement learning for manned unmanned teaming with enforced safety gates, rules of engagement, engagement authorization, and AI decision logs that record every call the system made and why. Deep RL foundations completed (Stanford XCS224R). In stealth.

---

## 2026 AI Projects

Ordered by current priority. Most projects are developed in private repositories. Public repos are linked.

| Project | Status | Repo | Focus |
| :--- | :--- | :--- | :--- |
| Assurance Gate | Live | [Space](https://huggingface.co/spaces/N20X/assurance-gate) and [GitHub](https://github.com/BRKMYR/assurance-gate) | Release gate over eval results: thresholds hashed before the run, Clopper Pearson bounds, parameter space coverage, paired regression, assurance case with linked evidence. Live on a static Space. |
| Waymax Safety Monitor | Shipped | Private | Risk ranked fleet dashboard for robotaxi teleoperators: three scenarios, seven trigger kinds, rewindable timeline on the Waymo Open Motion Dataset. |
| AV Safety Benchmark | Shipped | Private | Vendor neutral safety scorecard: 60 scenarios, four families, one composite score. 180 runs against three baselines. |
| World Model Benchmark | v0.2 | Private | World foundation model evaluation: six metrics, six failure modes, closed form baselines, toy suite leaderboard. |
| INTENT Operator Console | Shipped | Private | Manned unmanned teaming C2 console over a PettingZoo MARL testbed: tasking, engagement authorization, AI decision logs. |
| SAR Intelligence Pipeline | Shipped | Private | Five notebooks from Sentinel-1 tiles to a shareable GeoJSON intelligence product, free data only. |
| SAR VLM | Shipped | Private | Natural language analyst console for radar scenes: counts with a confidence trace, refusals where physics forbids an answer. |
| Adversarial Robustness Toolkit | Active | Public | PyTorch adversarial robustness toolkit for neural network defense. See [`pytorch-shield`](https://github.com/BRKMYR/pytorch-shield). |
| Deep RL Foundations | Completed | Private | Policy gradients, model based RL, robot learning. Stanford XCS224R Deep Reinforcement Learning plus HuggingFace Deep RL implementations. |
| Synthetic Data Generation | In progress | Private | Domain randomized pipelines for long tail coverage with NVIDIA Omniverse Replicator and procedural scenario generation. |
| Deep RL for Robotics | In progress | Private | Legged locomotion and manipulation: terrain adaptation, contact rich tasks, sim to real in MuJoCo and Isaac Gym. |

---

## How I Work

I run an AI augmented **PM Operating System** across three environments:

| Context | Tooling | Use Case |
| :--- | :--- | :--- |
| **Personal / AI Builder** | Claude Code (personalized) | GitHub projects, research synthesis, personal productivity |
| **Enterprise PM** | M365 Copilot | Product strategy, roadmaps, business models, stakeholder communication |
| **Production Engineering** | Amazon Kiro | Requirements driven implementation tracking and status visibility |

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **ML / RL** | PyTorch, JAX, Stable Baselines3, PettingZoo, Ray RLlib |
| **Robotics & Simulation** | ROS2, Gazebo, YARP, MuJoCo, Isaac Gym |
| **Safety** | UL 4600, SOTIF (ISO 21448), Waymax, adversarial robustness (PyTorch) |
| **Synthetic Data & World Models** | NVIDIA Omniverse Replicator, Waymo Open Motion Dataset, procedural generation |
| **SAR / EO** | Rasterio, GDAL, SentinelHub, STAC, vision language models |
| **AI Tooling** | Claude Code, M365 Copilot, Amazon Kiro |

---

## What I Believe

AI is moving into the physical world. Models will commoditize. The platforms that make them safe to deploy will not. That is where to build and where to bet.
