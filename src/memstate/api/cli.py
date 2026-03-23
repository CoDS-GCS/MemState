def main() -> None:
    import uvicorn

    from memstate.config import get_settings

    s = get_settings()
    uvicorn.run(
        "memstate.api.main:app",
        host=s.api_host,
        port=s.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
