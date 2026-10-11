declare namespace Api {
  namespace Catalyst {
    interface TopicTarget {
      group?: string;
      topicId?: string;
      topicName: string;
    }

    interface Impact {
      confidence: number;
      date: string;
      detailedAnalysis?: string;
      globalCoupling: string;
      id: number;
      impactLabel: 'A' | 'B' | 'C' | 'D' | 'S';
      impactLevel: number;
      lifecycleStage: string;
      messageSummary: string;
      messageTime?: string;
      messageType: string;
      predictedEffect: string;
      remainingInfluence: number;
      targetTopics: TopicTarget[];
    }

    interface SystemState {
      date: string;
      evolutionDirection?: string;
      evolutionNote?: string;
      globalCoupling: string;
      overallNote?: string;
      overallPhase: string;
      sentiment?: string;
      sentimentIndicators?: Record<string, number>;
      topicStates: Record<string, { note?: string; phase: string; trend?: string }>;
    }

    interface ActiveMessage {
      currentStage: string;
      dailyUpdates?: Array<Record<string, unknown>>;
      expectedDecayDate?: string;
      id: number;
      impactId: number;
      impactLabel: string;
      impactLevel: number;
      messageSummary: string;
      remainingInfluence: number;
      targetTopics: TopicTarget[];
    }

    interface Prediction {
      confidence: number;
      id: number;
      prediction: string;
      status: 'falsified' | 'partially_verified' | 'pending' | 'verified';
      targetTopic: string;
      timeWindow: string;
    }

    interface GroupAccuracy {
      accuracyRate: number;
      total: number;
    }

    interface Accuracy {
      accuracyRate: number;
      byMessageType: Record<string, GroupAccuracy>;
      byTimeWindow?: Record<string, GroupAccuracy>;
      byTopic: Record<string, GroupAccuracy>;
      falsified: number;
      historicalRate?: number;
      partiallyVerified: number;
      pending?: number;
      recent30DaysRate?: number;
      total: number;
      trendDelta?: number;
      verified: number;
    }

    interface Dashboard {
      accuracy: Accuracy;
      activeMessageList: ActiveMessage[];
      recentPredictions: Prediction[];
      today: {
        activeMessages: number;
        date: string;
        impacts: {
          aLevel: number;
          bLevel: number;
          cLevel: number;
          dLevel: number;
          sLevel: number;
          total: number;
        };
        pendingPredictions: number;
        systemState?: {
          globalCoupling: string;
          overallNote?: string;
          overallPhase: string;
          sentiment?: string;
        };
      };
    }
  }
}
