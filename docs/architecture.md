# Presentation architecture

Insert `architecture.svg` as a picture. It is a 1600 x 900 (16:9) vector diagram
with a white technical pipeline panel, teal title block, nested services, and technology
icons inspired by the previous-year reference in image.png. Endpoints, ports and tunnel details are omitted
for readability. React and FastAPI use recognizable technology symbols; camera, GPU, storage and monitor icons are schematic.

The five blocks are camera/recipe inputs, local inspection, evidence storage,
remote Cosmos Reason and operator review. Explanations return through the local
service; Cosmos cannot override measured findings. Inputs are currently recordings.
Third-vial reference comparisons are retrospective.

Editable Mermaid equivalent:

```mermaid
flowchart LR
    INPUT[Camera and recipe data\nVial + tank recordings / recipe order]
    subgraph LOCAL[Local analysis]
        INSPECT[Inspection service\nDetect / align / measure / compare]
        STORE[(Evidence store\nImages / measurements / records)]
        INSPECT --> STORE
    end
    AI[Cosmos Reason / remote GPU\nAdvisory descriptions + explanations]
    UI[Operator dashboard\nIndicators / batch review / CSV]
    INPUT --> INSPECT
    INSPECT <-->|Images + context / explanation| AI
    INSPECT -->|Findings + explanations| UI
    classDef input fill:#e5f3f5,stroke:#4c91a1,color:#203249
    classDef local fill:#e7effa,stroke:#4f7cb2,color:#203249
    classDef ai fill:#f0eafa,stroke:#8c74b9,color:#203249
    classDef ui fill:#e8f3ef,stroke:#558e81,color:#203249
    class INPUT input
    class INSPECT,STORE local
    class AI ai
    class UI ui
```

The earliest minimal illustration remains in `architecture-simple.svg`.

