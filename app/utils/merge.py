from typing import Any


def _is_object(value: Any) -> bool:
    # JS `typeof x === "object" && x !== null` -> dict or list
    return isinstance(value, (dict, list))


def smart_merge(target: Any, source: Any) -> Any:
    if not _is_object(target) or not _is_object(source):
        return source

    if isinstance(source, list):
        if not isinstance(target, list):
            return source

        is_keyed_array = (
            len(source) > 0 and isinstance(source[0], dict) and "objectId" in source[0]
        )

        if is_keyed_array:
            # dict preserves insertion order like JS Map; later duplicates overwrite earlier ones
            target_map: dict[Any, Any] = {
                (item.get("objectId") if isinstance(item, dict) else None): item
                for item in target
            }

            for source_item in source:
                object_id = source_item.get("objectId") if isinstance(source_item, dict) else None
                if object_id and object_id in target_map:
                    existing_item = target_map[object_id]
                    target_map[object_id] = smart_merge(existing_item, source_item)
                elif object_id:
                    # Add new item
                    target_map[object_id] = source_item

            return list(target_map.values())
        return source

    # 3. Handle Objects (Recursive Step)
    if isinstance(target, list):
        # JS spread of an array into an object yields index-keyed entries
        target = {str(i): v for i, v in enumerate(target)}

    output = dict(target)
    for key, value in source.items():
        if value is None:
            pass
        elif key in target:
            output[key] = smart_merge(target[key], value)
        else:
            output[key] = value

    return output
