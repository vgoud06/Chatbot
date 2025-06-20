import torch
import torch.nn as nn
from torch.nn import functional as F
import mmap
import random
import pickle
import os
from torch.amp import autocast, GradScaler

device = 'cuda' if torch.cuda.is_available() else 'cpu'

batch_size = 128    
block_size = 256
max_iters = 200000
learning_rate = 3e-4
eval_iters = 50
n_embd = 384
n_head = 8
n_layer = 8
dropout = 0.2

# Checkpoint settings
checkpoint_path = 'model_checkpoint.pth'
save_every = 500  # Save checkpoint every N iterations

print(device)

chars = ""
with open('vocab.txt', 'r', encoding='utf-8') as f:
    text = f.read()
    chars = sorted(list(set(text)))
    
vocab_size = len(chars)

string_to_int = { ch:i for i, ch in enumerate(chars) }
int_to_string = { i:ch for i, ch in enumerate(chars) }
encode = lambda s: [string_to_int[c] for c in s]
decode = lambda l: ''.join([int_to_string[i] for i in l])

def get_random_chunk(split):
    filename = "train_split.txt" if split == "train" else "val_split.txt"
    with open(filename, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            file_size = len(mm)
            start_pos = random.randint(0, (file_size) - block_size*batch_size)
    
            mm.seek(start_pos)
            block = mm.read(block_size*batch_size-1)
    
            decoded_block = block.decode('utf-8', errors='ignore').replace('\r', '')
    
            data = torch.tensor(encode(decoded_block), dtype=torch.long, device=device)
        return data

def get_batch(split):
    data = get_random_chunk(split)
    ix = torch.randint(len(data) - block_size, (batch_size,), device=device)
    x = torch.stack([data[i:i+block_size] for i in ix])
    y = torch.stack([data[i+1:i+block_size+1] for i in ix])
    x, y = x.to(device), y.to(device)
    return x, y

@torch.no_grad()
def estimate_loss():
    out = {}
    model.eval()
    for split in ['train', 'val']:
        losses = torch.zeros(eval_iters, device=device)
        for k in range(eval_iters):
            X, Y = get_batch(split)
            logits, loss = model(X, Y)
            losses[k] = loss.item()
        out[split] = losses.mean()
    model.train()
    torch.cuda.empty_cache()
    return out

def save_checkpoint(model, optimizer, iteration, loss, path):
    """Save model checkpoint"""
    checkpoint = {
        'iteration': iteration,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'loss': loss,
        'hyperparameters': {
            'vocab_size': vocab_size,
            'n_embd': n_embd,
            'n_head': n_head,
            'n_layer': n_layer,
            'block_size': block_size,
            'dropout': dropout
        }
    }
    torch.save(checkpoint, path)
    print(f"Checkpoint saved at iteration {iteration}")

def load_checkpoint(model, optimizer, path):
    """Load model checkpoint"""
    checkpoint = torch.load(path, map_location=device)
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    iteration = checkpoint['iteration']
    loss = checkpoint['loss']
    print(f"Checkpoint loaded from iteration {iteration}, loss: {loss:.4f}")
    return iteration, loss

class Head(nn.Module):
    """ one head of self-attention """

    def __init__(self, head_size):
        super().__init__()
        self.key = nn.Linear(n_embd, head_size, bias=False)
        self.query = nn.Linear(n_embd, head_size, bias=False)
        self.value = nn.Linear(n_embd, head_size, bias=False)
        self.register_buffer('tril', torch.tril(torch.ones(block_size, block_size, device=device)))

        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        # input of size (batch, time-step, channels)
        # output of size (batch, time-step, head size)
        B,T,C = x.shape
        k = self.key(x) # (B,T,hs)
        q = self.query(x) # (B,T,hs)
        # compute attention scores ("affinities")
        wei = q @ k.transpose(-2,-1) * k.shape[-1]**-0.5 # (B,T,hs) @ (B, hs, T) -> (B, T, T)
        wei = wei.masked_fill(self.tril[:T, :T] == 0, float('-inf')) # (B, T, T)
        wei = F.softmax(wei, dim=-1) # (B, T, T)
        wei = self.dropout(wei)
        # perform the weighted aggregation of the values
        v = self.value(x) # (B, T, hs)
        out = wei @ v # (B, T, T) @ (B, T, hs) -> (B, T, hs)
        return out
        
class MultiHeadAttention(nn.Module):
    """ multiple heads of self-attention in parallel """

    def __init__(self, num_heads, head_size):
        super().__init__()
        self.heads = nn.ModuleList([Head(head_size) for _ in range(num_heads)])
        self.proj = nn.Linear(head_size * num_heads, n_embd)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        out = torch.cat([h(x) for h in self.heads], dim=-1)
        out = self.dropout(self.proj(out))
        return out

class FeedForward(nn.Module):
    """ a simple linear layer followed by a non-linearity """

    def __init__(self, n_embd):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.ReLU(),
            nn.Linear(4 * n_embd, n_embd),
            nn.Dropout(dropout),
        )

    def forward(self, x):
        return self.net(x)

class Block(nn.Module):
    """Transformer block: communication followed by computation """

    def __init__(self, n_embd, n_head):
        # n_embd: embedding dimension, n_head: the number of heads we'd like
        super().__init__()
        head_size = n_embd // n_head
        self.sa = MultiHeadAttention(n_head, head_size)
        self.ffwd = FeedForward(n_embd)
        self.ln1 = nn.LayerNorm(n_embd)
        self.ln2 = nn.LayerNorm(n_embd)

    def forward(self, x):
        y = self.sa(x)
        x = self.ln1(x + y)
        y = self.ffwd(x)
        x = self.ln2(x + y)
        return x
        
class ChatbotLanguageModel(nn.Module):
    def __init__(self, vocab_size):
        super().__init__()
        self.token_embedding_table = nn.Embedding(vocab_size, n_embd)
        self.position_embedding_table = nn.Embedding(block_size, n_embd)
        self.blocks = nn.Sequential(*[Block(n_embd, n_head=n_head) for _ in range(n_layer)])
        self.ln_f = nn.LayerNorm(n_embd) # final norm layer
        self.lm_head = nn.Linear(n_embd, vocab_size)

        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean = 0.0, std=0.2)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.2)

    def forward(self, index, targets=None):
        B, T = index.shape

        # idx and targets are both (B, T) tensor of integers
        tok_emb = self.token_embedding_table(index) # (B, T, C)
        pos_emb = self.position_embedding_table(torch.arange(T, device=index.device)) # (T, C)
        x = tok_emb + pos_emb # (B,T,C)
        x = self.blocks(x) # (B,T,C)
        x = self.ln_f(x) # (B,T,C)
        logits = self.lm_head(x) # (B,T,vocab_size)

        if targets is None:
            loss = None
        else:
            B, T, C = logits.shape
            logits = logits.view(B*T, C)
            targets = targets.view(B*T)
            loss = F.cross_entropy(logits, targets)
            
        return logits, loss

    def generate(self, index, max_new_tokens):
        # index is (B, T) array of indices in the current context
        for _ in range(max_new_tokens):
            # get the predictions
            index_condensed = index[:, -block_size:]
            logits, loss = self.forward(index_condensed)
            # focus only on the last time step
            logits = logits[:, -1, :] # becomes (B, C)
            # apply softmax to get probabilities
            probs = F.softmax(logits, dim=-1) # (B, C)
            # sample from the distribution
            index_next = torch.multinomial(probs, num_samples=1) # (B, 1)
            # append sampled index to the running sequence
            index = torch.cat((index, index_next), dim=1) # (B, T+1)
        return index

# Initialize model
model = ChatbotLanguageModel(vocab_size)
model = model.to(device)

# Create optimizer
optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

# Load checkpoint if it exists
start_iter = 0
last_loss = None
if os.path.exists(checkpoint_path):
    start_iter, last_loss = load_checkpoint(model, optimizer, checkpoint_path)
    start_iter += 1  # Continue from next iteration
else:
    print("No checkpoint found. Starting from scratch.")

# Initialize loss variable (will be updated in training loop)
loss = None

# Training loop
for iter in range(start_iter, max_iters):
    if iter % eval_iters == 0:
        losses = estimate_loss()
        print(f"step: {iter}, train loss: {losses['train']:.3f}, val loss: {losses['val']:.3f}")

    # sample a batch of data
    xb, yb = get_batch('train')

    # evaluate the loss
    logits, loss = model.forward(xb, yb)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()
    
    # Save checkpoint periodically
    if iter % save_every == 0 and iter > 0:
        save_checkpoint(model, optimizer, iter, loss.item(), checkpoint_path)

# Handle case where training loop didn't execute (already at max_iters)
if loss is None:
    if last_loss is not None:
        print(f"Training already completed. Last recorded loss: {last_loss:.4f}")
        # Use the last loss for final save
        final_loss = last_loss
    else:
        # Calculate current loss if we don't have one
        print("Calculating current loss...")
        xb, yb = get_batch('train')
        logits, loss = model.forward(xb, yb)
        final_loss = loss.item()
        print(f"Current loss: {final_loss:.4f}")
else:
    final_loss = loss.item()
    print(f"Final loss: {final_loss:.4f}")

scaler = GradScaler(device='cuda')

for iter_num in range(start_iter, max_iters):
    xb, yb = get_batch('train')
    optimizer.zero_grad()
    with autocast():
        logits, loss = model(xb, yb)  # Your model returns both
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()

    torch.cuda.empty_cache()
    torch.cuda.ipc_collect()


# Save final model
save_checkpoint(model, optimizer, max_iters, final_loss, checkpoint_path)
print('Final model saved')

# Also save the model in the old pickle format for compatibility
with open('model-01.pk1', 'wb') as f:
    pickle.dump(model, f)
print('Model also saved in pickle format')