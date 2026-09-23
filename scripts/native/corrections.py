"""Narrow source adaptations justified by retained actual-executable witnesses."""

import re


def validate_ecbs_options(tree, name):
    """Reject a mode that ECBS::selectNode cannot handle, even in release builds."""
    if not name.startswith("eecbs"):
        return
    path = tree / "src/driver.cpp"
    text = path.read_text()
    if "DEC_MAPF_ECBS_MODE" in text:
        return
    needle = "po::notify(vm);"
    assert text.count(needle) == 1
    guard = '''
    // DEC_MAPF_ECBS_MODE: ECBS has no ASTAR branch in selectNode.
    if (vm["highLevelSolver"].as<string>() == "A*" && vm["lowLevelSolver"].as<bool>())
    {
        cerr << "highLevelSolver=A* requires lowLevelSolver=false" << endl;
        return 2;
    }
'''
    path.write_text(text.replace(needle, needle + guard))


def rectangle_mdd_contract(tree, name):
    """Use strengthened rectangle splits only at their represented path depth.

    ECBS intentionally caches shortest relaxed MDDs, which may be shorter than
    an absorbing-goal feasible path. Such MDDs remain admissible lower-bound
    abstractions. They cannot justify indexing or splitting a longer path.
    """
    path = tree / "src/RectangleReasoning.cpp"
    text = path.read_text()
    if "DEC_MAPF_RECTANGLE_DEPTH" in text:
        return
    start = text.index("shared_ptr<Conflict> RectangleReasoning::run(")
    opening = text.index("{", start) + 1
    uses_mdd = (
        "true"
        if name.startswith("eecbs")
        else (
            "strategy == rectangle_strategy::RM || strategy == rectangle_strategy::GR "
            "|| strategy == rectangle_strategy::DR"
        )
    )
    guard = """
    // DEC_MAPF_RECTANGLE_DEPTH: a relaxed shortest MDD can be shorter than
    // the current feasible path. Fall back to ordinary CBS splitting; clipping
    // indices would not establish the preconditions of a rectangle constraint.
    if (timestep < 0 || a1 < 0 || a2 < 0 ||
        a1 >= static_cast<int>(paths.size()) || a2 >= static_cast<int>(paths.size()) ||
        paths[a1] == nullptr || paths[a2] == nullptr ||
        timestep >= static_cast<int>(paths[a1]->size()) ||
        timestep >= static_cast<int>(paths[a2]->size()))
        return nullptr;
    if ((USES_MDD) && (mdd1 == nullptr || mdd2 == nullptr ||
        mdd1->levels.size() != paths[a1]->size() ||
        mdd2->levels.size() != paths[a2]->size()))
        return nullptr;
""".replace("USES_MDD", uses_mdd)
    path.write_text(text[:opening] + guard + text[opening:])


def apply(tree, name):
    validate_ecbs_options(tree, name)
    # Heap predicates require a strict, deterministic ordering. Historical predicates
    # compare a node greater than itself and some toss a coin on every comparison.
    # Equal keys stay equivalent; no random comparator can change between calls.
    for relative in [
        "inc/CBSNode.h",
        "inc/ECBSNode.h",
        "inc/SingleAgentSolver.h",
        "src/SingleAgentSolver.cpp",
        "src/MDD.cpp",
    ]:
        source = tree / relative
        if not source.exists():
            continue
        content = source.read_text()
        content = re.sub(r"(return n1[^;\n]*?)>=", r"\1>", content)
        content = re.sub(r"(return n1[^;\n]*?)<=", r"\1<", content)
        content = content.replace("return rand() % 2 == 0;", "return false;")
        content = content.replace("return rand() % 2;", "return false;")
        content = content.replace(
            "return false;   // break ties randomly",
            "return false;   // equivalent keys",
        )
        source.write_text(content)
    rectangle_mdd_contract(tree, name)
    # Fail rather than silently reapply a patch to an unexpected source version.
    path = tree / "src/SpaceTimeAStar.cpp"
    text = path.read_text()
    if "DEC_MAPF_ABSORBING" in text:
        return
    if name == "eecbs-stay":
        needle = "\t\tif (curr->timestep >= constraint_table.length_max)"
        assert text.count(needle) == 1
        text = text.replace(
            needle,
            "\t\t// DEC_MAPF_ABSORBING: an early goal visit cannot later depart.\n"
            "\t\tif (curr->location == goal_location) continue;\n\n" + needle,
        )
    elif name == "cbsh2":
        # Both shortest-path overloads must respect first-arrival absorption.
        for indent in ["\t\t", "        "]:
            needle = indent + "if (curr->timestep >= constraint_table.length_max)"
            assert text.count(needle) == 1
            text = text.replace(
                needle,
                indent
                + "// DEC_MAPF_ABSORBING\n"
                + indent
                + "if (curr->location == goal_location) continue;\n\n"
                + needle,
            )
        # Actual route construction is separate from the relaxed travel-time bound.
        routes, travel = text.split("int SpaceTimeAStar::getTravelTime", 1)
        assert routes.count("next_locations.emplace_back(curr->location);") == 3
        routes = routes.replace(
            "next_locations.emplace_back(curr->location);",
            "if (!NO_WAIT) next_locations.emplace_back(curr->location);",
        )
        text = routes + "int SpaceTimeAStar::getTravelTime" + travel
        cmake = tree / "CMakeLists.txt"
        cmake.write_text(
            cmake.read_text() + "\nadd_compile_definitions(NO_WAIT=${NO_WAIT})\n"
        )
    path.write_text(text)
    if name == "cbsh2":
        path = tree / "src/CorridorReasoning.cpp"
        text = path.read_text()
        # A degree-two cycle has no corridor endpoints. The historical scan never
        # terminates on a 2x2 open map; returning no specialized conflict restores
        # the ordinary CBS conflict split, with all legal solutions retained.
        text = text.replace(
            "    rst.push_front(curr);\n    auto neighbors",
            "    rst.push_front(curr);\n    std::set<int> visited{root, curr};\n    auto neighbors",
        )
        for push in ["front", "back"]:
            needle = f"        rst.push_{push}(next);"
            assert text.count(needle) == 1
            text = text.replace(
                needle,
                "        if (!visited.insert(next).second) return {};\n" + needle,
            )
        text = text.replace(
            "    rst.push_back(curr);\n    neighbors",
            "    if (!visited.insert(curr).second) return {};\n    rst.push_back(curr);\n    neighbors",
        )
        # Case 100: generalized corridor-target split excludes a valid cost-10
        # solution and returns 11 as "Optimal". Both starts and both targets are
        # inside the same corridor, with an outside bypass. Use the standard
        # conflict here rather than an unproved strengthened length split.
        needle = "\tif ((max(start[0], entry[0]) - max(start[1], entry[1]))"
        assert text.count(needle) == 1
        text = text.replace(
            needle,
            "\tif (start[0] >= 0 && start[1] >= 0 && goal[0] >= 0 && goal[1] >= 0)\n"
            "\t\treturn nullptr; // Generalized split is not valid for this case.\n"
            + needle,
        )
        path.write_text(text)
