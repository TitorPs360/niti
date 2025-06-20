# Niti Frontend - Interactive Detective Game

นิติ (Niti) is an AI-powered murder mystery detective game with an interactive React frontend.

## Features

- **Game Setup & Management**: Initialize game services and generate mystery scenarios
- **Character Interaction**: Chat with AI-powered characters to gather clues
- **Evidence Examination**: View and analyze crime scene evidence
- **Real-time Updates**: Live polling of game state and generation progress
- **Thai Language Support**: Fully localized interface and character interactions

## Architecture

### Components

- **GameSetup**: Handles initial game setup and content generation
- **GameBoard**: Main game interface with tabbed navigation
- **CharacterCard**: Display character information with portraits
- **ChatInterface**: Real-time chat with AI characters
- **EvidenceCard**: Evidence display with image viewing

### State Management

- **useGameState**: Custom hook for managing overall game state
- **GameAPI**: Service layer for backend communication
- **Real-time Polling**: Automatic state updates during setup/generation

### Game Flow

1. **Setup Phase**: Configure services and AI models
2. **Generation Phase**: Create mystery scenario and character images
3. **Playing Phase**: Investigate characters and examine evidence
4. **Restart**: Clear all data and begin fresh case

## API Integration

Connects to backend at `http://localhost:8001/api` with endpoints:

- `POST /game/setup` - Initialize game services
- `POST /game/start` - Begin content generation
- `GET /game/state` - Check current status
- `GET /game/script/{id}` - Retrieve generated mystery
- `POST /game/chat` - Interact with characters
- `GET /game/image/{id}` - Display AI-generated images
- `POST /game/restart` - Reset game state

## Getting Started

### Prerequisites

- Node.js 16+ and npm
- Backend services running (see main project README)

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm start

# Build for production
npm run build
```

### Development

The app will run at `http://localhost:3000` and automatically connect to the backend API.

For development with backend services:

```bash
# In project root directory
docker-compose up -d

# In frontend directory
npm start
```

## Technology Stack

- **React 19** with TypeScript
- **Tailwind CSS** for styling
- **Custom Hooks** for state management
- **Fetch API** for HTTP requests
- **CSS Animations** for loading states

## Character AI System

Characters use contextual AI responses based on:
- Character profile and personality
- Hidden secrets and motives
- Previous conversation history
- Case-specific knowledge
- Thai language roleplay prompts

## Image Generation

- AI-generated character portraits using Flux
- Crime scene evidence photography
- Real-time generation status updates
- Full-screen image viewing

## Game Logic

- Tab-based navigation (Overview, Characters, Evidence)
- Real-time chat with conversation memory
- Progress tracking through game phases
- Error handling and recovery

## Deployment

Build the production version:

```bash
npm run build
```

Serve static files or deploy to hosting platform like Vercel, Netlify, or AWS S3.

## Customization

### Styling

Modify `tailwind.config.js` for theme customization:

```javascript
theme: {
  extend: {
    colors: {
      'custom-blue': '#your-color',
    },
  },
}
```

### API Configuration

Update `src/services/api.ts` to change backend URL:

```typescript
const API_BASE = 'https://your-backend-url/api';
```

### Language Support

Extend translations in component files or add i18n library for multi-language support.