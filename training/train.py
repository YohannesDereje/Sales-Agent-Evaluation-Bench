"""
Tenacious-Bench v0.1 — LoRA SFT Training Script (Path A)

Path A: Supervised Fine-Tuning of the outreach generation component.
Framework: Unsloth + TRL SFTTrainer
Backbone: Qwen/Qwen2.5-1.5B-Instruct (4-bit LoRA)
Hardware: Google Colab T4 (fp16, 15 GB VRAM)

Run:
    python training/train.py

Outputs:
    training/training_run.log   -- JSON log with hyperparams + loss curve
    (adapter pushed to HuggingFace Hub if HF_TOKEN is set)
"""

import json
import os
import random
import time
from pathlib import Path

import numpy as np
import torch

# ---------------------------------------------------------------------------
# Hyperparameters — all explicit, nothing implicit
# ---------------------------------------------------------------------------

BACKBONE        = "unsloth/Qwen2.5-1.5B-Instruct"   # pinned Unsloth mirror
HF_REVISION     = "main"   # set to a commit SHA for full reproducibility
                            # e.g. "a8d4e2f" — re-run `git ls-remote` on the HF repo

LORA_R          = 16        # LoRA rank
LORA_ALPHA      = 32        # LoRA alpha (scale = alpha / r = 2.0)
LORA_DROPOUT    = 0.05
# Q and V projections update attention routing — what the model looks for and what values
# flow forward when a match fires. This is sufficient for SUPPRESSION tasks (teaching the
# model NOT to produce banned phrases), which are routing behaviors.
# It is NOT sufficient for GENERATION tasks that require composing specific new output
# phrases (e.g. "curious whether", "if your team") — those require FFN updates because the
# FFN layers (gate_proj, up_proj, down_proj) are the per-token key-value memories where
# token-level generative capacity lives (Geva et al. 2021). The 3 residual SOC failures in
# ablations/held_out_traces.jsonl (regex_negative PASS, regex_positive FAIL) are the
# empirical signature of this limitation.
#
# v0.1 config — Q+V routing only (sufficient for suppression, insufficient for generation)
LORA_TARGETS    = ["q_proj", "v_proj"]

# v0.2 recommended config — add FFN targets for generative phrase composition:
# LORA_TARGETS  = ["q_proj", "v_proj", "gate_proj", "up_proj", "down_proj"]
# Expected: regex_positive pass-rate on SOC jumps from 6/9 to 8-9/9;
# regex_negative pass-rate stays at 9/9 (suppression already worked).
# Re-evaluate rank r=16 after adding FFN targets — effective param count grows ~4x.

LEARNING_RATE   = 2e-4
LR_SCHEDULER    = "linear"  # linear warmup then linear decay
WARMUP_RATIO    = 0.03       # 3% of total steps for warmup
EPOCHS          = 3
PER_DEVICE_BATCH = 2
GRAD_ACCUM      = 4         # effective batch size = 2 * 4 = 8
MAX_SEQ_LENGTH  = 1024      # tokens; set to 1024 to avoid cross-entropy shape mismatch
FP16            = True

SEED            = 42        # fixed for reproducibility

TRAIN_FILE      = "training_data/sft_pairs_filtered.jsonl"
OUTPUT_DIR      = "training/checkpoints"
LOG_FILE        = "training/training_run.log"
HF_REPO         = "Yohannesdn/tenacious-outreach-lora-qwen-1.5b"   # upload target

# ---------------------------------------------------------------------------
# Seed everything before any model initialisation
# ---------------------------------------------------------------------------

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(SEED)

# ---------------------------------------------------------------------------
# Load model + tokenizer via Unsloth
# ---------------------------------------------------------------------------

from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name    = BACKBONE,
    revision      = HF_REVISION,
    max_seq_length = MAX_SEQ_LENGTH,
    dtype         = None,       # auto-detect: fp16 on T4
    load_in_4bit  = True,
)

# Apply LoRA — only q_proj and v_proj; all other weights frozen
model = FastLanguageModel.get_peft_model(
    model,
    r                = LORA_R,
    lora_alpha       = LORA_ALPHA,
    lora_dropout     = LORA_DROPOUT,
    target_modules   = LORA_TARGETS,
    bias             = "none",
    use_gradient_checkpointing = "unsloth",
    random_state     = SEED,
    use_rslora       = False,
    loftq_config     = None,
)

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total     = sum(p.numel() for p in model.parameters())
print(f"Trainable parameters: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

# ---------------------------------------------------------------------------
# Dataset — load SFT pairs
# ---------------------------------------------------------------------------

from datasets import Dataset

def load_sft_pairs(path: str) -> Dataset:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return Dataset.from_list(records)

train_dataset = load_sft_pairs(TRAIN_FILE)
print(f"Training pairs loaded: {len(train_dataset)}")

# Format as chat-template text for SFTTrainer
def format_chat(example):
    messages = example.get("messages", example.get("conversations", []))
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}

train_dataset = train_dataset.map(format_chat)

# ---------------------------------------------------------------------------
# Loss logger — writes per-step loss to training_run.log
# ---------------------------------------------------------------------------

class StepLossLogger:
    """Logs loss at each logging step; writes final JSON summary on close."""

    def __init__(self, log_path: str):
        self.log_path  = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict] = []
        self._start  = time.time()

    def record(self, step: int, loss: float, lr: float):
        self.steps.append({"step": step, "loss": round(loss, 6), "lr": lr})
        print(f"  step={step:4d}  loss={loss:.4f}  lr={lr:.2e}")

    def close(self, final_loss: float):
        runtime = time.time() - self._start
        summary = {
            "backbone":          BACKBONE,
            "hf_revision":       HF_REVISION,
            "lora_r":            LORA_R,
            "lora_alpha":        LORA_ALPHA,
            "lora_dropout":      LORA_DROPOUT,
            "lora_targets":      LORA_TARGETS,
            "learning_rate":     LEARNING_RATE,
            "lr_scheduler":      LR_SCHEDULER,
            "warmup_ratio":      WARMUP_RATIO,
            "epochs":            EPOCHS,
            "per_device_batch":  PER_DEVICE_BATCH,
            "grad_accum":        GRAD_ACCUM,
            "max_seq_length":    MAX_SEQ_LENGTH,
            "fp16":              FP16,
            "seed":              SEED,
            "train_pairs":       len(train_dataset),
            "train_runtime_s":   round(runtime, 3),
            "final_train_loss":  round(final_loss, 7),
            "loss_curve":        self.steps,
        }
        self.log_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nTraining log written -> {self.log_path}")
        print(f"Runtime: {runtime:.1f}s  Final loss: {final_loss:.4f}")

logger = StepLossLogger(LOG_FILE)

# Custom callback to capture per-step loss
from transformers import TrainerCallback

class LossLogCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs and "loss" in logs:
            lr = logs.get("learning_rate", 0.0)
            logger.record(state.global_step, logs["loss"], lr)

# ---------------------------------------------------------------------------
# SFTTrainer — Path A (Supervised Fine-Tuning)
# ---------------------------------------------------------------------------

from trl import SFTTrainer
from transformers import TrainingArguments

training_args = TrainingArguments(
    output_dir              = OUTPUT_DIR,
    num_train_epochs        = EPOCHS,
    per_device_train_batch_size = PER_DEVICE_BATCH,
    gradient_accumulation_steps = GRAD_ACCUM,
    learning_rate           = LEARNING_RATE,
    lr_scheduler_type       = LR_SCHEDULER,
    warmup_ratio            = WARMUP_RATIO,
    fp16                    = FP16,
    bf16                    = False,
    logging_steps           = 10,
    save_strategy           = "epoch",
    seed                    = SEED,
    data_seed               = SEED,
    report_to               = "none",   # W&B/TensorBoard off; using StepLossLogger
    optim                   = "adamw_8bit",
)

trainer = SFTTrainer(
    model           = model,
    tokenizer       = tokenizer,
    train_dataset   = train_dataset,
    dataset_text_field = "text",
    max_seq_length  = MAX_SEQ_LENGTH,
    args            = training_args,
    callbacks       = [LossLogCallback()],
)

# Confirm only LoRA weights are trainable (sanity check)
frozen = sum(1 for n, p in model.named_parameters() if not p.requires_grad)
print(f"Frozen layers: {frozen}  (all non-LoRA weights confirmed frozen)")

# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------

print(f"\nStarting SFT training — backbone={BACKBONE}  seed={SEED}")
result = trainer.train()

final_loss = result.training_loss
logger.close(final_loss)

# ---------------------------------------------------------------------------
# Push adapter to HuggingFace Hub
# ---------------------------------------------------------------------------

hf_token = os.environ.get("HF_TOKEN", "").strip()
if hf_token:
    print(f"\nPushing LoRA adapter to {HF_REPO} …")
    model.push_to_hub(HF_REPO, token=hf_token)
    tokenizer.push_to_hub(HF_REPO, token=hf_token)
    print("Adapter pushed successfully.")
else:
    print("\nHF_TOKEN not set — skipping HuggingFace push.")
    print(f"To push manually: model.push_to_hub('{HF_REPO}', token='<your_token>')")
