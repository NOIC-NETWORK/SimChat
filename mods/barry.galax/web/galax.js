class GalaxEngine {
    constructor(chatInstance) {
        this.chatInstance = chatInstance;
        this.currentStep = 0;
        this.isRunning = false;
        this.results = {
            recall: null,
            hypotheses: null,
            evidence: null,
            synthesis: null
        };
        this.stepNames = ['recall', 'hypothesis', 'evidence', 'synthesis'];
        this.stepTitles = ['召回阶段', '假设生成', '证据加权', '结论合成'];
    }

    async query(userInput, requestSeq) {
        if (this.isRunning) return;
        
        this.isRunning = true;
        this.replayMode = false;
        this.currentStep = 0;
        this.results = {
            recall: null,
            hypotheses: null,
            evidence: null,
            synthesis: null
        };

        this.chatInstance.hideWelcome();
        this.chatInstance.addMessage('user', userInput);
        this.showProcessingIndicator();

        try {
            const response = await fetch('/api/rigard/galax/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: userInput,
                    session_id: this.chatInstance.sessionId
                })
            });

            const data = await response.json();
            
            if (requestSeq !== undefined && requestSeq !== this.chatInstance.requestSeq) {
                this.removeProcessingIndicator();
                return;
            }

            this.removeProcessingIndicator();

            if (data.success) {
                if (data.threat_detection && data.threat_detection.is_threat_detected) {
                    this.chatInstance.showThreatAlert(data.threat_detection);
                    if (data.emergency_response) {
                        this.chatInstance.addMessage('ai', data.emergency_response);
                        this.chatInstance.refreshSessionList();
                        return;
                    }
                }
                await this.renderResults(data);
                this.chatInstance.refreshSessionList();
            } else {
                this.chatInstance.addMessage('ai', '抱歉，Galax推理引擎暂时无法响应，请稍后再试。');
            }
        } catch (error) {
            if (requestSeq !== undefined && requestSeq !== this.chatInstance.requestSeq) return;
            this.removeProcessingIndicator();
            this.chatInstance.addMessage('ai', '网络连接出错，请检查网络后重试。');
        } finally {
            this.isRunning = false;
            if (requestSeq === undefined || requestSeq === this.chatInstance.requestSeq) {
                this.chatInstance.isTyping = false;
                this.chatInstance.updateSubmitBtnState();
            }
        }
    }

    showProcessingIndicator() {
        const processingDiv = document.createElement('div');
        processingDiv.className = 'message ai';
        processingDiv.id = 'galaxProcessing';
        
        processingDiv.innerHTML = `
            <div class="message-avatar ai">
                <img src="/rigard/sprites/logos/rigard.png" alt="Rigard">
            </div>
            <div class="message-content">
                <div class="message-bubble">
                    <div class="galax-progress">
                        <div class="galax-step" id="galax-step-0">
                            <div class="galax-step-dot"></div>
                            <span class="galax-step-label">召回</span>
                        </div>
                        <div class="galax-step" id="galax-step-1">
                            <div class="galax-step-dot"></div>
                            <span class="galax-step-label">假设</span>
                        </div>
                        <div class="galax-step" id="galax-step-2">
                            <div class="galax-step-dot"></div>
                            <span class="galax-step-label">证据</span>
                        </div>
                        <div class="galax-step" id="galax-step-3">
                            <div class="galax-step-dot"></div>
                            <span class="galax-step-label">合成</span>
                        </div>
                    </div>
                    <div class="galax-status-text" id="galax-status">正在执行Galax推理引擎...</div>
                </div>
            </div>
        `;
        
        this.chatInstance.messagesList.appendChild(processingDiv);
        this.chatInstance.scrollToBottom();
    }

    updateProcessingStep(stepIndex) {
        const statusText = document.getElementById('galax-status');
        if (statusText) {
            statusText.textContent = `${this.stepTitles[stepIndex]}...`;
        }

        for (let i = 0; i < 4; i++) {
            const stepDiv = document.getElementById(`galax-step-${i}`);
            if (stepDiv) {
                const dot = stepDiv.querySelector('.galax-step-dot');
                if (i < stepIndex) {
                    stepDiv.classList.add('completed');
                    stepDiv.classList.remove('active');
                } else if (i === stepIndex) {
                    stepDiv.classList.add('active');
                    stepDiv.classList.remove('completed');
                } else {
                    stepDiv.classList.remove('active', 'completed');
                }
            }
        }
    }

    removeProcessingIndicator() {
        const processingDiv = document.getElementById('galaxProcessing');
        if (processingDiv) {
            processingDiv.remove();
        }
    }

    async renderResults(data) {
        this.results = data.result;

        if (this.results.recall) {
            await this.renderRecall(this.results.recall);
        }

        if (this.results.hypotheses) {
            await this.renderHypotheses(this.results.hypotheses);
        }

        if (this.results.evidence) {
            await this.renderEvidence(this.results.evidence);
        }

        if (this.results.synthesis) {
            await this.renderSynthesis(this.results.synthesis);
        }
    }

    async replayResults(result) {
        this.replayMode = true;
        try {
            await this.renderResults({ result: result });
        } finally {
            this.replayMode = false;
        }
    }

    async renderRecall(recallData) {
        const content = document.createElement('div');
        content.className = 'galax-recall';
        
        let sourcesHtml = '';
        if (recallData.sources && recallData.sources.length > 0) {
            sourcesHtml = recallData.sources.map((source, index) => `
                <div class="galax-source-item">
                    <span class="galax-source-index">${index + 1}.</span>
                    <span class="galax-source-title">${source.title}</span>
                    <span class="galax-source-source">(${source.source})</span>
                </div>
            `).join('');
        }

        content.innerHTML = `
            <div class="galax-section-header">
                <span class="galax-section-icon">🔍</span>
                <span class="galax-section-title">召回阶段</span>
                <span class="galax-section-count">(${recallData.sources?.length || 0}个来源)</span>
            </div>
            <div class="galax-summary">${recallData.summary}</div>
            <div class="galax-sources">${sourcesHtml}</div>
        `;
        
        this.chatInstance.addMessage('ai', content);
        await this.delay(500);
    }

    async renderHypotheses(hypotheses) {
        const content = document.createElement('div');
        content.className = 'galax-hypotheses';
        
        const hypothesesHtml = hypotheses.map((hypo, index) => `
            <div class="galax-hypothesis-item">
                <span class="galax-hypothesis-number">H${index + 1}</span>
                <div class="galax-hypothesis-content">${hypo}</div>
            </div>
        `).join('');

        content.innerHTML = `
            <div class="galax-section-header">
                <span class="galax-section-icon">💡</span>
                <span class="galax-section-title">假设生成</span>
                <span class="galax-section-desc">基于检索结果，生成3个可能的结论</span>
            </div>
            <div class="galax-hypotheses-list">${hypothesesHtml}</div>
        `;
        
        this.chatInstance.addMessage('ai', content);
        await this.delay(500);
    }

    async renderEvidence(evidence) {
        const content = document.createElement('div');
        content.className = 'galax-evidence';
        
        const evidenceHtml = evidence.map((item, index) => {
            const confidenceClass = item.confidence === '高' ? 'confidence-high' : 'confidence-low';
            return `
                <div class="galax-evidence-item">
                    <div class="galax-evidence-header">
                        <span class="galax-evidence-number">E${index + 1}</span>
                        <span class="galax-evidence-confidence ${confidenceClass}">${item.confidence}置信度</span>
                    </div>
                    <div class="galax-evidence-hypothesis">${item.hypothesis}</div>
                    <div class="galax-evidence-details">
                        <div class="galax-evidence-support">
                            <span class="galax-evidence-label">支持证据：</span>
                            <span>${item.supporting}</span>
                        </div>
                        <div class="galax-evidence-refute">
                            <span class="galax-evidence-label">反驳观点：</span>
                            <span>${item.refuting || '无'}</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        content.innerHTML = `
            <div class="galax-section-header">
                <span class="galax-section-icon">⚖️</span>
                <span class="galax-section-title">证据加权</span>
                <span class="galax-section-desc">对每个假设进行证据验证</span>
            </div>
            <div class="galax-evidence-list">${evidenceHtml}</div>
        `;
        
        this.chatInstance.addMessage('ai', content);
        await this.delay(500);
    }

    async renderSynthesis(synthesis) {
        const content = document.createElement('div');
        content.className = 'galax-synthesis';
        
        content.innerHTML = `
            <div class="galax-section-header">
                <span class="galax-section-icon">🎯</span>
                <span class="galax-section-title">结论合成</span>
            </div>
            <div class="galax-synthesis-conclusion">${synthesis.conclusion}</div>
            ${synthesis.sarcastic_comment ? `
            <div class="galax-synthesis-comment">
                <span class="galax-comment-label">毒舌解说：</span>
                <span>${synthesis.sarcastic_comment}</span>
            </div>
            ` : ''}
            <div class="galax-synthesis-sources">
                <span class="galax-sources-label">参考来源：</span>
                <span>${synthesis.references}</span>
            </div>
        `;
        
        this.chatInstance.addMessage('ai', content);
    }

    delay(ms) {
        if (this.replayMode) return Promise.resolve();
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    isEnabled() {
        return true;
    }
}

// SimChat MOD 注册：宿主按 `chat.mode` 元数据动态加载本文件后实例化引擎。
(function () {
    const registry = window.SimChatModes || (window.SimChatModes = {
        _factories: {},
        register(id, factory) {
            this._factories[id] = factory;
        },
        create(id, chatInstance) {
            const factory = this._factories[id];
            return factory ? factory(chatInstance) : null;
        }
    });
    registry.register('galax', (chatInstance) => new GalaxEngine(chatInstance));
})();