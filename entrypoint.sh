#!/bin/bash
set -e

# ============================================================
# Pearl Miner — All-in-One Entrypoint
# Starts: pearld (node) → pearl-gateway (miner) → vLLM (inference)
# ============================================================

echo "🐚 Pearl Miner starting up..."
echo "   Wallet: ${PEARL_WALLET_ADDRESS:-NOT SET}"
echo "   GPU Memory Utilization: ${PEARL_GPU_UTIL:-0.9}"
echo "   Max Model Length: ${PEARL_MAX_MODEL_LEN:-8192}"

# Validate required env vars
if [ -z "$PEARL_WALLET_ADDRESS" ]; then
    echo "❌ ERROR: PEARL_WALLET_ADDRESS is required!"
    echo "   Set it to your prl1... address"
    exit 1
fi

if [ -z "$HF_TOKEN" ]; then
    echo "❌ ERROR: HF_TOKEN is required!"
    echo "   Get one at https://huggingface.co/settings/tokens"
    exit 1
fi

# Export HF token for model download
export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"

# ============================================================
# Step 1: Start Pearl full node
# ============================================================
echo "📦 Starting Pearl node (pearld)..."

# Create chain data directory
mkdir -p /app/chain-data

# Generate random RPC credentials for internal use
RPC_USER="miner_$(head -c 8 /dev/urandom | xxd -p)"
RPC_PASS="$(head -c 16 /dev/urandom | xxd -p)"

# Start pearld
pearld \
    --datadir=/app/chain-data \
    --rpcuser="$RPC_USER" \
    --rpcpass="$RPC_PASS" \
    --miningaddr="$PEARL_WALLET_ADDRESS" \
    --listen=:44108 \
    --rpclisten=:44107 \
    &
PEARLD_PID=$!

# Wait for node RPC to be ready
echo "⏳ Waiting for Pearl node to start..."
for i in $(seq 1 60); do
    if curl -s --user "$RPC_USER:$RPC_PASS" \
        --data-binary '{"jsonrpc":"1.0","id":"startup","method":"getinfo","params":[]}' \
        -H 'content-type: text/plain;' \
        http://localhost:44107/ > /dev/null 2>&1; then
        echo "✅ Pearl node is running"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "❌ Pearl node failed to start after 60s"
        exit 1
    fi
    sleep 1
done

# Show sync status
BLOCK_COUNT=$(curl -s --user "$RPC_USER:$RPC_PASS" \
    --data-binary '{"jsonrpc":"1.0","id":"sync","method":"getblockcount","params":[]}' \
    -H 'content-type: text/plain;' \
    http://localhost:44107/ | jq -r '.result // "unknown"')
echo "📊 Current block height: $BLOCK_COUNT (chain will sync in background)"

# ============================================================
# Step 2: Start Pearl Gateway (the mining bridge)
# ============================================================
echo "⛏️  Starting Pearl Gateway..."

export PEARLD_RPC_URL="http://localhost:44107"
export PEARLD_RPC_USER="$RPC_USER"
export PEARLD_RPC_PASSWORD="$RPC_PASS"
export PEARLD_MINING_ADDRESS="$PEARL_WALLET_ADDRESS"

pearl-gateway start &
GATEWAY_PID=$!

# Wait for gateway metrics endpoint
echo "⏳ Waiting for gateway to be ready..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8339/metrics > /dev/null 2>&1; then
        echo "✅ Pearl Gateway is running"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "⚠️  Gateway not responding on :8339 yet, continuing anyway..."
    fi
    sleep 1
done

# ============================================================
# Step 3: Auto-detect GPUs and start vLLM
# ============================================================
if [ -z "$CUDA_VISIBLE_DEVICES" ]; then
    GPU_COUNT=$(nvidia-smi -L 2>/dev/null | wc -l)
    if [ "$GPU_COUNT" -gt 1 ]; then
        CUDA_VISIBLE_DEVICES=$(seq -s, 0 $((GPU_COUNT - 1)))
        export CUDA_VISIBLE_DEVICES
        echo "🎮 Auto-detected $GPU_COUNT GPUs: CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
    fi
fi

echo "🚀 Starting vLLM inference server (this mines PRL!)..."
echo "   Model: pearl-ai/Llama-3.3-70B-Instruct-pearl"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Mining will begin once the chain is synced."
echo "  First sync takes ~2 hours from genesis."
echo "  Monitor: http://localhost:8339/metrics"
echo "  Check your stats: https://lordofpearls.xyz"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Start vLLM (this is the main process — keeps container alive)
exec vllm serve pearl-ai/Llama-3.3-70B-Instruct-pearl \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len "${PEARL_MAX_MODEL_LEN:-8192}" \
    --gpu-memory-utilization "${PEARL_GPU_UTIL:-0.9}" \
    --enforce-eager
