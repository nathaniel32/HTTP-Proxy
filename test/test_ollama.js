const BASE_URL = 'http://localhost:8080';

async function ollamaRequest(path, options = {}) {
    const url = `${BASE_URL}${path}`;
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };

    try {
        const response = await fetch(url, {
            ...options,
            headers
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${await response.text()}`);
        }

        return response;
    } catch (error) {
        console.error(`Request failed: ${error.message}`);
        throw error;
    }
}

// Test 1: Chat Completion (Non-Streaming)
async function testChatNonStreaming() {
    console.log('\nTest 1: Chat Completion (Non-Streaming)');
    const response = await ollamaRequest('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
            model: 'gemma3:4b',
            messages: [
                { role: 'user', content: 'Say hello in one sentence' }
            ],
            stream: false
        })
    });

    const data = await response.json();
    console.log('Response:', data.message.content);
    console.log('Tokens:', data.eval_count);
}

// Test 2: Chat Completion (Streaming)
async function testChatStreaming() {
    console.log('\nTest 2: Chat Completion (Streaming)');
    const response = await ollamaRequest('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
            model: 'gemma3:4b',
            messages: [
                { role: 'user', content: 'Count from 1 to 5' }
            ],
            stream: true
        })
    });

    console.log('Streaming response:');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const data = decoder.decode(value);
        const lines = data.split('\n').filter(line => line.trim());

        for (const line of lines) {
            try {
                const json = JSON.parse(line);
                if (json.message?.content) {
                    process.stdout.write(json.message.content);
                }
            } catch (e) {
                // Ignore non-JSON lines
            }
        }
    }
    console.log('\nStream complete');
}

// Test 3: Generate Text
async function testGenerate() {
    console.log('\nTest 3: Generate Text');
    const response = await ollamaRequest('/api/generate', {
        method: 'POST',
        body: JSON.stringify({
            model: 'gemma3:4b',
            prompt: 'What is 2+2?',
            stream: false
        })
    });

    const data = await response.json();
    console.log('Response:', data.response);
}

// Test 4: List Models
async function testListModels() {
    console.log('\nTest 4: List Models');
    const response = await ollamaRequest('/api/tags', {
        method: 'GET'
    });

    const data = await response.json();
    console.log('Available models:');
    data.models.forEach(model => {
        console.log(`  - ${model.name} (${(model.size / 1e9).toFixed(2)} GB)`);
    });
}

// Test 5: Show Model Info
async function testShowModel() {
    console.log('\nTest 5: Show Model Info');
    const response = await ollamaRequest('/api/show', {
        method: 'POST',
        body: JSON.stringify({
            name: 'gemma3:4b'
        })
    });

    const data = await response.json();
    console.log('Model info:');
    console.log(`- Family: ${data.details?.family || 'N/A'}`);
    console.log(`- Parameters: ${data.details?.parameter_size || 'N/A'}`);
    console.log(`- Quantization: ${data.details?.quantization_level || 'N/A'}`);
}

// Test 6: Embeddings (Optional)
async function testEmbeddings() {
    console.log('\nTest 6: Embeddings');
    try {
        const response = await ollamaRequest('/api/embeddings', {
            method: 'POST',
            body: JSON.stringify({
                model: 'gemma3:4b',
                prompt: 'Hello world'
            })
        });

        const data = await response.json();
        console.log('Embedding vector length:', data.embedding?.length || 0);
    } catch (error) {
        console.log('Skipped: Model does not support embeddings');
    }
}

// Test 7: Multiple Concurrent Requests
async function testConcurrent() {
    console.log('\nTest 7: Concurrent Requests');
    const promises = [];
    
    for (let i = 1; i <= 3; i++) {
        promises.push(
            ollamaRequest('/api/generate', {
                method: 'POST',
                body: JSON.stringify({
                    model: 'gemma3:4b',
                    prompt: `Say number ${i}`,
                    stream: false
                })
            }).then(r => r.json())
        );
    }

    const results = await Promise.all(promises);
    console.log('All concurrent requests completed:');
    results.forEach((data, idx) => {
        console.log(`  Request ${idx + 1}: ${data.response?.substring(0, 50)}...`);
    });
}

// Run all tests
async function runAllTests() {
    console.log('Testing Ollama API\n');
    console.log('=' .repeat(60));

    try {
        await testChatNonStreaming();
        await testChatStreaming();
        await testGenerate();
        await testListModels();
        await testShowModel();
        await testEmbeddings();
        await testConcurrent();

        console.log('\n' + '='.repeat(60));
        console.log('All tests completed successfully!');
    } catch (error) {
        console.error('\nTest suite failed:', error.message);
        process.exit(1);
    }
}

runAllTests();
