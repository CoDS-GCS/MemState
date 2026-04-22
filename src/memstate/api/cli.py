def main() -> None:
    import uvicorn

    from memstate.config import get_settings

    s = get_settings()
    browse_host = "127.0.0.1" if s.api_host in ("0.0.0.0", "::") else s.api_host
    print(f"MemState API: open http://{browse_host}:{s.api_port}/ in your browser")
    uvicorn.run(
        "memstate.api.main:app",
        host=s.api_host,
        port=s.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
