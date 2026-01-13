# TubeMind Docker Setup

This Docker configuration containerizes the TubeMind backend API (excluding the UI folder).

## Files Included

- **Dockerfile** - Multi-stage Docker image for the FastAPI application
- **docker-compose.yml** - Orchestration file for running the containerized application
- **.dockerignore** - Excludes unnecessary files from the Docker build context

## Environment Variables Setup

⚠️ **Important**: The `.env` file is NOT copied into the Docker image for security reasons. 

### For Local Development (Docker Compose)
Create a `.env.local` file in the project root:
```
GROQ_API_KEY=your_key_here
SECRET_KEY=your_secret_key
ALGORITHM=HS256
DATABASE_URL=sqlite:///./analytics.db
```

### For Render.com Deployment
Set environment variables directly in your Render service dashboard:
1. Go to your Render service
2. Navigate to **Environment** tab
3. Add the following variables:
   - `GROQ_API_KEY` - Your Groq API key
   - `SECRET_KEY` - A secure secret key for JWT
   - `ALGORITHM` - HS256 (or your preferred algorithm)
   - Any other required environment variables

**Do NOT commit `.env` files to git** - they should only exist locally or be set via Render's dashboard.

## Build & Run

### Using Docker Compose (Recommended for Local Development)

```bash
# Create .env.local file with your variables
echo "GROQ_API_KEY=your_key_here" > .env.local
echo "SECRET_KEY=your_secret_key" >> .env.local
echo "ALGORITHM=HS256" >> .env.local

# Build and run the container
docker-compose up -d

# View logs
docker-compose logs -f tubemind-api

# Stop the container
docker-compose down

# Rebuild the image
docker-compose up -d --build
```

### Using Docker Directly

```bash
# Build the image
docker build -t tubemind-api:latest .

# Run the container
docker run -d \
  --name tubemind-api \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/chroma_db_advanced:/app/chroma_db_advanced \
  -v $(pwd)/chroma_db_agents:/app/chroma_db_agents \
  -v $(pwd)/chroma_db_citations:/app/chroma_db_citations \
  -v $(pwd)/chroma_db_citations_v2:/app/chroma_db_citations_v2 \
  -v $(pwd)/chroma_db_pro:/app/chroma_db_pro \
  -v $(pwd)/chroma_db_resources:/app/chroma_db_resources \
  -v $(pwd)/chroma_db_resources_v2:/app/chroma_db_resources_v2 \
  -v $(pwd)/chroma_db_sessions:/app/chroma_db_sessions \
  -v $(pwd)/chroma_db_ultimate:/app/chroma_db_ultimate \
  tubemind-api:latest
```

## Access the Application
Required Environment Variables

Make sure these variables are set either in `.env.local` (local) or Render dashboard (production):

```
GROQ_API_KEY=your_groq_api_key
SECRET_KEY=your_jwt_secret_key
ALGORITHM=HS256
```

Optional database URL (defaults to SQLite):
````.env` file includes the required environment variables:

```
GROQ_API_KEY=your_key_here
SECRET_KEY=your_secret_key
ALGORITHM=HS256
DATABASE_URL=sqlite:///./analytics.db
```

## Data Persistence

The Docker setup includes volumes for ChromaDB collections and database files:

- All ChromaDB directories are persisted as Docker volumes
- SQLite database files are mounted directly
- Data persists even when containers are stopped

## Optional Services

The `docker-compose.yml` includes commented-out services:

- **PostgreSQL**: Uncomment if you want to use PostgreSQL instead of SQLite
- **Redis**: Uncomment for caching support

## Troubleshooting

### Container won't start
```bash.local file exists and has correct variables
cat .env.local
```

### Missing environment variables error
If you see "environment variable not found":
- **Local**: Create/update `.env.local` with required variables
- **Render**: Add the missing variables in the Render dashboard Environment tabker-compose logs tubemind-api

# Verify the .env file exists and has correct variables
cat .env
```

### Database/Volume issues
```bash
# Clean up volumes (WARNING: deletes data)
docker-compose down -v

# Recreate from scratch
docker-compose up -d --build
```

### Port conflicts
If port 8000 is already in use, modify the port mapping in `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Access at localhost:8001
```Deployment to Render.com

### Steps:
1. Push your code to GitHub (excluding `.env`)
2. Create a new service on Render.com
3. Connect your GitHub repository
4. Set the build command: (leave default or empty)
5. Set the start command: `uvicorn main:app --host 0.0.0.0 --port 8000`
6. Go to **Environment** tab and add all required variables
7. Deploy!

### Render Environment Variables Example:
```
GROQ_API_KEY=gsk_xxxxx
SECRET_KEY=your-super-secret-key-here
ALGORITHM=HS256
```

## Notes

- The UI folder is excluded from the Docker build
- Run the UI separately or use a reverse proxy (nginx) if needed
- The application runs on port 8000 inside the container
- All ChromaDB data is persistent across container restarts
- `.env` files are NOT included in the Docker image (security best practice)
- Use Render's Environment dashboard to manage production secre
- Non-root user runs the application for security
- Health checks monitor container status automatically

## Notes

- The UI folder is excluded from the Docker build
- Run the UI separately or use a reverse proxy (nginx) if needed
- The application runs on port 8000 inside the container
- All ChromaDB data is persistent across container restarts
