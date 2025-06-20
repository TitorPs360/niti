import React, { useState } from 'react';
import { Character, DeductionResponse } from '../types/game';
import { GameAPI } from '../services/api';

interface DeductionModalProps {
  gameId: string;
  characters: Character[];
  onClose: () => void;
  onRestart: () => void;
}

export const DeductionModal: React.FC<DeductionModalProps> = ({
  gameId,
  characters,
  onClose,
  onRestart,
}) => {
  const [selectedCulprit, setSelectedCulprit] = useState('');
  const [reasoning, setReasoning] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<DeductionResponse | null>(null);

  const handleSubmit = async () => {
    if (!selectedCulprit.trim() || !reasoning.trim()) {
      alert('กรุณาเลือกผู้ต้องสงสัยและให้เหตุผล');
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await GameAPI.submitDeduction({
        game_id: gameId,
        culprit: selectedCulprit,
        reasoning: reasoning.trim(),
      });
      setResult(response);
    } catch (err) {
      console.error('Failed to submit deduction:', err);
      alert('ไม่สามารถส่งการทายได้ กรุณาลองใหม่');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleNewGame = () => {
    onRestart();
    onClose();
  };

  if (result) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] overflow-auto">
          <div className="p-6">
            {/* Result Header */}
            <div className="text-center mb-6">
              {result.correct ? (
                <div>
                  <div className="text-6xl mb-4">🎉</div>
                  <h2 className="text-2xl font-bold text-green-600 mb-2">ยินดีด้วย!</h2>
                  <p className="text-lg text-gray-700">คุณทายถูกต้อง!</p>
                </div>
              ) : (
                <div>
                  <div className="text-6xl mb-4">😔</div>
                  <h2 className="text-2xl font-bold text-red-600 mb-2">เสียใจด้วย</h2>
                  <p className="text-lg text-gray-700">คุณทายผิด</p>
                </div>
              )}
            </div>

            {/* Score */}
            <div className="text-center mb-6">
              <div className="text-3xl font-bold text-blue-600 mb-2">
                คะแนน: {result.score}/100
              </div>
              {!result.correct && (
                <p className="text-gray-600">
                  ผู้กระทำผิดจริง: <span className="font-semibold">{result.actual_culprit}</span>
                </p>
              )}
            </div>

            {/* AI Judgment */}
            <div className="mb-6">
              <h3 className="text-lg font-semibold text-gray-800 mb-3">ความเห็นจากผู้พิพากษา</h3>
              <div className="bg-gray-50 p-4 rounded-lg border">
                <p className="text-gray-700 leading-relaxed">{result.judgment}</p>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex space-x-3">
              <button
                onClick={handleNewGame}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-md transition duration-200"
              >
                เล่นเกมใหม่
              </button>
              <button
                onClick={onClose}
                className="flex-1 bg-gray-600 hover:bg-gray-700 text-white font-medium py-3 px-4 rounded-md transition duration-200"
              >
                ปิด
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-800">สรุปการสืบสวน</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="space-y-6">
            {/* Culprit Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-3">
                ใครคือผู้กระทำผิด?
              </label>
              <div className="space-y-2">
                {characters.map((character) => (
                  <label
                    key={character.name}
                    className="flex items-center p-3 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer"
                  >
                    <input
                      type="radio"
                      name="culprit"
                      value={character.name}
                      checked={selectedCulprit === character.name}
                      onChange={(e) => setSelectedCulprit(e.target.value)}
                      className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
                    />
                    <div className="ml-3">
                      <div className="text-sm font-medium text-gray-900">
                        {character.name}
                      </div>
                      <div className="text-sm text-gray-500">
                        {character.role} • อายุ {character.age} ปี
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* Reasoning */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                เหตุผลในการทาย
              </label>
              <textarea
                value={reasoning}
                onChange={(e) => setReasoning(e.target.value)}
                placeholder="อธิบายเหตุผลของคุณ อ้างอิงหลักฐานและการสนทนากับตัวละคร..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 h-32 resize-none"
                disabled={isSubmitting}
              />
              <p className="text-xs text-gray-500 mt-1">
                การให้เหตุผลที่ดีจะได้คะแนนโบนัส
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200">
          <div className="flex space-x-3">
            <button
              onClick={handleSubmit}
              disabled={isSubmitting || !selectedCulprit.trim() || !reasoning.trim()}
              className="flex-1 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-medium py-3 px-4 rounded-md transition duration-200 flex items-center justify-center"
            >
              {isSubmitting ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  กำลังประเมิน...
                </>
              ) : (
                'ส่งการทาย'
              )}
            </button>
            <button
              onClick={onClose}
              disabled={isSubmitting}
              className="px-6 py-3 text-gray-600 hover:text-gray-800 font-medium transition duration-200"
            >
              ยกเลิก
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};