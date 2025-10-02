import os
import random
from typing import List, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim


class DuelingDQN(nn.Module):
    def __init__(self, input_dim: int, output_dim: int):
        super().__init__()
        hidden = 128
        self.feature = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.value_stream = nn.Sequential(
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1),
        )
        self.adv_stream = nn.Sequential(
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        f = self.feature(x)
        value = self.value_stream(f)
        adv = self.adv_stream(f)
        q = value + adv - adv.mean(dim=1, keepdim=True)
        return q


class PERBuffer:
    def __init__(self, capacity: int = 100000, alpha: float = 0.6):
        self.capacity = capacity
        self.alpha = alpha
        self.buffer: List[Tuple[np.ndarray, int, float, np.ndarray, bool]] = []
        self.priorities: List[float] = []
        self.pos = 0

    def __len__(self):
        return len(self.buffer)

    def append(self, state, action, reward, next_state, done, priority: float = None):
        if priority is None:
            priority = 1.0
        if len(self.buffer) < self.capacity:
            self.buffer.append((state, action, reward, next_state, done))
            self.priorities.append(priority)
        else:
            self.buffer[self.pos] = (state, action, reward, next_state, done)
            self.priorities[self.pos] = priority
            self.pos = (self.pos + 1) % self.capacity

    def sample(self, batch_size: int, beta: float = 0.4):
        if len(self.buffer) == 0:
            raise ValueError("PERBuffer is empty")
        prios = np.array(self.priorities, dtype=np.float64)
        scaled = prios ** self.alpha
        probs = scaled / scaled.sum()
        indices = np.random.choice(len(self.buffer), batch_size, p=probs)
        samples = [self.buffer[i] for i in indices]
        # Importance-sampling weights
        total = len(self.buffer)
        weights = (total * probs[indices]) ** (-beta)
        weights /= weights.max()
        states, actions, rewards, next_states, dones = zip(*samples)
        return (
            np.stack(states),
            np.array(actions),
            np.array(rewards, dtype=np.float32),
            np.stack(next_states),
            np.array(dones, dtype=np.float32),
            indices,
            weights.astype(np.float32),
        )

    def update_priorities(self, indices, new_prios):
        for idx, p in zip(indices, new_prios):
            self.priorities[int(idx)] = float(abs(p) + 1e-6)


class DQNAgent:
    def __init__(self, state_size, action_size):
        self.device = torch.device("cpu")
        self.action_size = action_size

        self.model = DuelingDQN(state_size, action_size).to(self.device)
        self.target_model = DuelingDQN(state_size, action_size).to(self.device)
        self.update_target_model()

        self.optimizer = optim.Adam(self.model.parameters(), lr=1e-3)
        self.gamma = 0.99

        # Exploration
        self.epsilon = 1.0
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.995

        # PER
        self.memory = PERBuffer(capacity=100_000, alpha=0.6)
        self.beta = 0.4
        self.beta_increment = 1e-4

        # Target update
        self.train_step = 0
        self.target_update_interval = 1000

    def update_target_model(self):
        self.target_model.load_state_dict(self.model.state_dict())

    def remember(self, s, a, r, s2, done):
        # Use max priority by default to ensure new samples are seen
        max_prio = max(self.memory.priorities) if len(self.memory) > 0 else 1.0
        self.memory.append(s, a, r, s2, done, priority=max_prio)

    def act(self, state, action_mask: np.ndarray | None = None):
        if (self.epsilon > np.random.random()):
            if action_mask is None:
                return random.randrange(self.action_size)
            valid_indices = np.flatnonzero(action_mask)
            if len(valid_indices) == 0:
                return random.randrange(self.action_size)
            return int(np.random.choice(valid_indices))

        state_t = torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            q_values = self.model(state_t).squeeze(0).cpu().numpy()
        if action_mask is not None:
            q_values = q_values.copy()
            q_values[~action_mask.astype(bool)] = -1e9
        return int(q_values.argmax())

    def replay(self, batch_size):
        if len(self.memory) < batch_size:
            return

        states, actions, rewards, next_states, dones, indices, is_weights = self.memory.sample(batch_size, beta=self.beta)
        self.beta = min(1.0, self.beta + self.beta_increment)

        states_t = torch.as_tensor(states, dtype=torch.float32, device=self.device)
        actions_t = torch.as_tensor(actions, dtype=torch.long, device=self.device).unsqueeze(1)
        rewards_t = torch.as_tensor(rewards, dtype=torch.float32, device=self.device)
        next_states_t = torch.as_tensor(next_states, dtype=torch.float32, device=self.device)
        dones_t = torch.as_tensor(dones, dtype=torch.float32, device=self.device)
        is_w_t = torch.as_tensor(is_weights, dtype=torch.float32, device=self.device)

        # Current Q estimates
        q_pred = self.model(states_t).gather(1, actions_t).squeeze(1)

        # Double DQN target
        next_actions = self.model(next_states_t).argmax(dim=1, keepdim=True)
        next_q_target = self.target_model(next_states_t).gather(1, next_actions).squeeze(1)
        target = rewards_t + (1.0 - dones_t) * self.gamma * next_q_target.detach()

        td_error = target - q_pred
        loss = (is_w_t * td_error.pow(2)).mean()

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=10.0)
        self.optimizer.step()

        # Update priorities
        td_abs = td_error.detach().abs().cpu().numpy() + 1e-6
        self.memory.update_priorities(indices, td_abs)

        # Epsilon decay
        if self.epsilon > self.epsilon_min:
            self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        # Target update by steps
        self.train_step += 1
        if self.train_step % self.target_update_interval == 0:
            self.update_target_model()

        return float(loss.item())

    def load(self, filename):
        path = filename
        if not os.path.isabs(filename):
            path = os.path.join("models", filename)
        state_dict = torch.load(path, map_location=self.device)
        # Load into current architecture if shapes align
        try:
            self.model.load_state_dict(state_dict)
        except Exception as e:
            print(f"Warning: could not load weights directly into dueling network: {e}")
        self.model.eval()
        print(f"Loaded model weights from {path}")