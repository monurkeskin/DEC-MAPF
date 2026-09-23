// Actual RectangleReasoning boundary witnesses; no solver substitute.
#include "RectangleReasoning.h"
#include <iostream>
#include <string>

void populate(MDD& mdd, const Path& path, size_t depth)
{
    mdd.levels.resize(depth);
    MDDNode* previous = nullptr;
    for (size_t t = 0; t < depth; ++t)
    {
        auto node = new MDDNode(path[t].location, previous);
        if (previous != nullptr) previous->children.push_back(node);
        mdd.levels[t].push_back(node);
        previous = node;
    }
}

int main(int argc, char** argv)
{
    if (argc != 2) return 2;
    const std::string mode(argv[1]);
    Instance instance;
    instance.num_of_cols = instance.num_of_rows = 4;
    instance.map_size = 16;
    RectangleReasoning reasoning(instance);
#if DEC_MAPF_CBS
    reasoning.strategy = rectangle_strategy::RM;
#endif
    Path first(5), second(5);
    const int a[] = {1, 5, 6, 10, 11};
    const int b[] = {4, 5, 9, 10, 14};
    for (size_t t = 0; t < 5; ++t)
    {
        first[t].location = a[t];
        second[t].location = b[t];
    }
    MDD mdd1, mdd2;
    populate(mdd1, first, mode == "short_first" ? 2 : mode == "empty" ? 0 : 5);
    populate(mdd2, second, mode == "short_second" ? 2 : 5);
    std::vector<Path*> paths{&first, &second};
    const int tick = mode == "negative_tick" ? -1 : mode == "late_tick" ? 5 : 1;
    const auto result = reasoning.run(paths, tick, 0, 1,
        mode == "null" ? nullptr : &mdd1, &mdd2);
    // A depth mismatch cannot justify a strengthened rectangle split.
    // Ordinary CBS splitting must remain available instead of clipping indices.
    if (mode != "matched" && result != nullptr) return 3;
#if !DEC_MAPF_CBS
    // Positive control: the guard must not disable valid rectangle reasoning.
    if (mode == "matched" && result == nullptr) return 4;
#endif
    std::cout << mode << ": safe; specialized conflict=" << bool(result) << '\n';
    return 0;
}
