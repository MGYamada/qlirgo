fn main() -> std::process::ExitCode {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let json = qlidoc_engine::support::report::json_requested(&args);
    qlidoc_engine::support::report::emit(qlidoc_engine::run(&args), json)
}
