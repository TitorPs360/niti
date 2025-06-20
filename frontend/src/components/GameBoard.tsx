import React, { useState, useEffect } from 'react';
import { GameScript, Character } from '../types/game';
import { CharacterCard } from './CharacterCard';
import { EvidenceCard } from './EvidenceCard';
import { ChatInterface } from './ChatInterface';
import { DebugPanel } from './DebugPanel';
import { DeductionModal } from './DeductionModal';
import { GameAPI } from '../services/api';

interface GameBoardProps {
  gameScript: GameScript;
  gameId: string;
  onRestart: () => void;
  onForceReloadScript?: () => void;
}

export const GameBoard: React.FC<GameBoardProps> = ({
  gameScript,
  gameId,
  onRestart,
  onForceReloadScript,
}) => {
  const [selectedCharacter, setSelectedCharacter] = useState<Character | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'characters' | 'evidence'>('overview');
  const [showDeductionModal, setShowDeductionModal] = useState(false);

  // Debug logging
  useEffect(() => {
    console.log('GameBoard received gameScript:', gameScript);
    console.log('Characters:', gameScript.people);
    console.log('Evidence:', gameScript.evidence);
    gameScript.people.forEach((character, index) => {
      console.log(`Character ${index}:`, character.name, 'image_id:', character.image_id);
    });
    gameScript.evidence.forEach((evidence, index) => {
      console.log(`Evidence ${index}:`, evidence.type, 'image_id:', evidence.image_id);
    });
  }, [gameScript]);
  useEffect(() => {
    loadCharacters();
  }, [gameId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadCharacters = async () => {
    try {
      await GameAPI.getGameCharacters(gameId);
      // Characters are already in gameScript.people, no need to store separately
    } catch (err) {
      console.error('Failed to load characters:', err);
    }
  };

  const handleCharacterClick = (character: Character) => {
    setSelectedCharacter(character);
  };

  const handleCloseChat = () => {
    setSelectedCharacter(null);
  };

  const handleSolveCase = () => {
    setShowDeductionModal(true);
  };

  const handleCloseDeduction = () => {
    setShowDeductionModal(false);
  };

  const TabButton = ({ tab, label, count }: { tab: string; label: string; count?: number }) => (
    <button
      onClick={() => setActiveTab(tab as any)}
      className={`
        px-4 py-2 text-sm font-medium rounded-lg transition-colors
        ${activeTab === tab
          ? 'bg-blue-600 text-white'
          : 'text-gray-600 hover:text-gray-800 hover:bg-gray-100'
        }
      `}
    >
      {label}
      {count !== undefined && (
        <span className={`ml-2 px-2 py-0.5 text-xs rounded-full ${
          activeTab === tab ? 'bg-blue-500' : 'bg-gray-200 text-gray-600'
        }`}>
          {count}
        </span>
      )}
    </button>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div>
              <h1 className="text-xl font-semibold text-gray-800">
                คดีฆาตกรรม: {gameScript.situation.victim}
              </h1>
              <p className="text-sm text-gray-600">
                {gameScript.situation.location} • {gameScript.situation.time}
              </p>
            </div>
            <div className="flex space-x-3">
              <button
                onClick={handleSolveCase}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-md text-sm font-medium transition duration-200"
              >
                สรุปคดี
              </button>
              <button
                onClick={onRestart}
                className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-md text-sm font-medium transition duration-200"
              >
                เริ่มเกมใหม่
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="bg-white shadow-sm border-t">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-2 py-4">
            <TabButton tab="overview" label="ภาพรวมคดี" />
            <TabButton tab="characters" label="ตัวละคร" count={gameScript.people.length} />
            <TabButton tab="evidence" label="หลักฐาน" count={gameScript.evidence.length} />
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Case Overview */}
            <div className="bg-white rounded-lg shadow-md p-6">
              <h2 className="text-xl font-semibold text-gray-800 mb-4">รายละเอียดคดี</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <h3 className="font-medium text-gray-700 mb-2">ข้อมูลเหยื่อ</h3>
                  <p className="text-gray-600 mb-1">
                    <strong>ชื่อ:</strong> {gameScript.situation.victim}
                  </p>
                  <p className="text-gray-600 mb-1">
                    <strong>อายุ:</strong> {gameScript.situation.age} ปี
                  </p>
                  <p className="text-gray-600">
                    <strong>สาเหตุการตาย:</strong> {gameScript.situation.cause_of_death}
                  </p>
                </div>
                <div>
                  <h3 className="font-medium text-gray-700 mb-2">ข้อมูลเหตุการณ์</h3>
                  <p className="text-gray-600 mb-1">
                    <strong>สถานที่:</strong> {gameScript.situation.location}
                  </p>
                  <p className="text-gray-600 mb-1">
                    <strong>เวลา:</strong> {gameScript.situation.time}
                  </p>
                </div>
              </div>
              {gameScript.situation.details && (
                <div className="mt-4 pt-4 border-t">
                  <h3 className="font-medium text-gray-700 mb-2">รายละเอียดเพิ่มเติม</h3>
                  <p className="text-gray-600">{gameScript.situation.details}</p>
                </div>
              )}
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-white rounded-lg shadow-md p-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-3">เริ่มการสืบสวน</h3>
                <p className="text-gray-600 mb-4">
                  สอบสวนตัวละครเพื่อหาความจริง
                </p>
                <button
                  onClick={() => setActiveTab('characters')}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium transition duration-200"
                >
                  ดูตัวละคร ({gameScript.people.length})
                </button>
              </div>
              
              <div className="bg-white rounded-lg shadow-md p-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-3">ตรวจสอบหลักฐาน</h3>
                <p className="text-gray-600 mb-4">
                  วิเคราะห์หลักฐานที่พบในที่เกิดเหตุ
                </p>
                <button
                  onClick={() => setActiveTab('evidence')}
                  className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-md text-sm font-medium transition duration-200"
                >
                  ดูหลักฐาน ({gameScript.evidence.length})
                </button>
              </div>
            </div>

            {/* Solve Case Call-to-Action */}
            <div className="bg-gradient-to-r from-orange-500 to-red-600 rounded-lg shadow-md p-6 text-white">
              <h3 className="text-lg font-semibold mb-3">พร้อมสรุปคดีแล้ว?</h3>
              <p className="mb-4 text-orange-100">
                เมื่อคุณรวบรวมหลักฐานและสอบสวนตัวละครครบถ้วนแล้ว สามารถสรุปคดีได้
              </p>
              <button
                onClick={handleSolveCase}
                className="bg-white text-orange-600 hover:bg-orange-50 px-6 py-3 rounded-md font-medium transition duration-200"
              >
                🔍 สรุปคดีและระบุผู้กระทำผิด
              </button>
            </div>
          </div>
        )}

        {activeTab === 'characters' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-md p-6">
              <h2 className="text-xl font-semibold text-gray-800 mb-4">ตัวละครที่เกี่ยวข้อง</h2>
              <p className="text-gray-600 mb-6">
                คลิกที่ตัวละครเพื่อเริ่มการสอบสวน
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {gameScript.people.map((character, index) => (
                  <CharacterCard
                    key={index}
                    character={character}
                    onClick={() => handleCharacterClick(character)}
                  />
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'evidence' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-md p-6">
              <h2 className="text-xl font-semibold text-gray-800 mb-4">หลักฐานที่พบ</h2>
              <p className="text-gray-600 mb-6">
                หลักฐานที่พบในที่เกิดเหตุและสถานที่ที่เกี่ยวข้อง
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {gameScript.evidence.map((evidence, index) => (
                  <EvidenceCard
                    key={index}
                    evidence={evidence}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Chat Interface Modal */}
      {selectedCharacter && (
        <ChatInterface
          character={selectedCharacter}
          gameId={gameId}
          onClose={handleCloseChat}
        />
      )}

      {/* Deduction Modal */}
      {showDeductionModal && (
        <DeductionModal
          gameId={gameId}
          characters={gameScript.people}
          onClose={handleCloseDeduction}
          onRestart={onRestart}
        />
      )}

      {/* Floating Solve Case Button */}
      {activeTab !== 'overview' && (
        <div className="fixed bottom-6 right-6 z-40">
          <button
            onClick={handleSolveCase}
            className="bg-gradient-to-r from-orange-500 to-red-600 hover:from-orange-600 hover:to-red-700 text-white px-6 py-3 rounded-full shadow-lg font-medium transition duration-200 flex items-center space-x-2"
          >
            <span>🔍</span>
            <span>สรุปคดี</span>
          </button>
        </div>
      )}

      {/* Debug Panel */}
      <DebugPanel gameScript={gameScript} gameId={gameId} onForceReload={onForceReloadScript} />
    </div>
  );
};