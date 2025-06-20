import React, { useState } from 'react';
import { GamePhase } from '../types/game';

interface GameSetupProps {
  phase: GamePhase;
  loading: boolean;
  error: string | null;
  onSetup: (ollamaModel?: string) => void;
  onStart: (extraPrompt?: string) => void;
}

export const GameSetup: React.FC<GameSetupProps> = ({
  phase,
  loading,
  error,
  onSetup,
  onStart,
}) => {
  const [ollamaModel, setOllamaModel] = useState('gemma3:27b');
  const [extraPrompt, setExtraPrompt] = useState('');

  const getPhaseMessage = () => {
    switch (phase) {
      case 'setup':
        return 'ระบบพร้อมสำหรับการตั้งค่า';
      case 'setting_up':
        return 'กำลังตั้งค่าระบบ...';
      case 'ready':
        return 'ระบบพร้อม! สามารถเริ่มเกมได้';
      case 'generating':
        return 'กำลังสร้างเนื้อหาเกม...';
      case 'setup_error':
        return 'เกิดข้อผิดพลาดในการตั้งค่า';
      case 'generation_error':
        return 'เกิดข้อผิดพลาดในการสร้างเกม';
      default:
        return `สถานะ: ${phase}`;
    }
  };

  const getPhaseColor = () => {
    switch (phase) {
      case 'setup':
        return 'text-blue-600';
      case 'setting_up':
      case 'generating':
        return 'text-yellow-600';
      case 'ready':
        return 'text-green-600';
      case 'setup_error':
      case 'generation_error':
        return 'text-red-600';
      default:
        return 'text-gray-600';
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-6 bg-white rounded-lg shadow-lg">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-800 mb-2">
          นิติ - เกมสืบสวนคดีฆาตกรรม
        </h1>
        <p className="text-gray-600">
          เกมสืบสวนคดีฆาตกรรมที่ใช้ AI สร้างเนื้อหา
        </p>
      </div>

      <div className="mb-6">
        <div className={`text-center text-lg font-medium ${getPhaseColor()}`}>
          {getPhaseMessage()}
        </div>
        
        {loading && (
          <div className="mt-4 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        )}
        
        {error && (
          <div className="mt-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}
      </div>

      {phase === 'setup' && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Ollama Model
            </label>
            <select
              value={ollamaModel}
              onChange={(e) => setOllamaModel(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="gemma3:27b">Gemma 3 27B (แนะนำ)</option>
              <option value="llama3:8b">Llama 3 8B</option>
              <option value="mistral:7b">Mistral 7B</option>
            </select>
          </div>
          
          <button
            onClick={() => onSetup(ollamaModel)}
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium py-2 px-4 rounded-md transition duration-200"
          >
            {loading ? 'กำลังตั้งค่า...' : 'ตั้งค่าระบบ'}
          </button>
        </div>
      )}

      {phase === 'ready' && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              คำแนะนำเพิ่มเติม (ไม่บังคับ)
            </label>
            <textarea
              value={extraPrompt}
              onChange={(e) => setExtraPrompt(e.target.value)}
              placeholder="เช่น: ต้องการให้เกิดเหตุในโรงพยาบาล หรือ มีตัวละครที่เป็นแพทย์"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 h-20 resize-none"
            />
          </div>
          
          <button
            onClick={() => onStart(extraPrompt.trim() || undefined)}
            disabled={loading}
            className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-medium py-2 px-4 rounded-md transition duration-200"
          >
            {loading ? 'กำลังสร้างเกม...' : 'เริ่มเกม'}
          </button>
        </div>
      )}

      {(phase === 'setup_error' || phase === 'generation_error') && (
        <div className="space-y-4">
          <button
            onClick={window.location.reload}
            className="w-full bg-red-600 hover:bg-red-700 text-white font-medium py-2 px-4 rounded-md transition duration-200"
          >
            รีเฟรชหน้า
          </button>
        </div>
      )}

      <div className="mt-8 text-sm text-gray-500 text-center">
        <p>เกมนี้ใช้ AI ในการสร้างเนื้อหา อาจใช้เวลาในการเตรียมพร้อม</p>
        <p>โปรดรอสักครู่...</p>
      </div>
    </div>
  );
};