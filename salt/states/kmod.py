"""
Loading and unloading of kernel modules
=======================================

The Kernel modules on a system can be managed cleanly with the kmod state
module:

.. code-block:: yaml

    add_kvm:
      kmod.present:
        - name: kvm_amd
    remove_beep:
      kmod.absent:
        - name: pcspkr

Multiple modules can be specified for both kmod.present and kmod.absent.

.. code-block:: yaml

    add_sound:
      kmod.present:
        - mods:
          - snd_hda_codec_hdmi
          - snd_hda_codec
          - snd_hwdep
          - snd_hda_core
          - snd_pcm
          - snd_timer
          - snd
"""


def __virtual__():
    """
    Only load if the kmod module is available in __salt__
    """
    if "kmod.available" in __salt__:
        return True
    return (False, "kmod module could not be loaded")


def _append_comment(ret, comment):
    """
    append ``comment`` to ``ret['comment']``
    """
    if ret["comment"]:
        ret["comment"] = ret["comment"].rstrip() + "\n" + comment
    else:
        ret["comment"] = comment

    return ret


def present(name, persist=False, mods=None):
    """
    Ensure that the specified kernel module is loaded

    name
        The name of the kernel module to verify is loaded

    persist
        Also add module to ``/etc/modules`` (or
        ``/etc/modules-load.d/salt_managed.conf`` if the ``systemd`` key is
        present in Grains.

    mods
        A list of modules to verify are loaded.  If this argument is used, the
        ``name`` argument, although still required, is not used, and becomes a
        placeholder

        .. versionadded:: 2016.3.0
    """
    if not isinstance(mods, (list, tuple)):
        mods = [name]
    ret = {"name": name, "result": True, "changes": {}, "comment": ""}

    loaded_mods = __salt__["kmod.mod_list"]()
    if persist:
        persist_mods = __salt__["kmod.mod_list"](True)
        # Intersection of loaded modules and persistent modules
        loaded_mods = list(set(loaded_mods) & set(persist_mods))

    # Intersection of loaded and proposed modules
    already_loaded = list(set(loaded_mods) & set(mods))
    if len(already_loaded) == 1:
        comment = f"Kernel module {already_loaded[0]} is already present"
        _append_comment(ret, comment)
    elif len(already_loaded) > 1:
        comment = "Kernel modules {} are already present".format(
            ", ".join(already_loaded)
        )
        _append_comment(ret, comment)

    if len(already_loaded) == len(mods):
        return ret  # all modules already loaded

    # Complement of proposed modules and already loaded modules
    not_loaded = list(set(mods) - set(already_loaded))

    if __opts__["test"]:
        ret["result"] = None
        if ret["comment"]:
            ret["comment"] += "\n"
        if len(not_loaded) == 1:
            comment = f"Kernel module {not_loaded[0]} is set to be loaded"
        else:
            comment = "Kernel modules {} are set to be loaded".format(
                ", ".join(not_loaded)
            )
        _append_comment(ret, comment)
        return ret

    # Complement of proposed, unloaded modules and available modules
    unavailable = list(set(not_loaded) - set(__salt__["kmod.available"]()))
    if unavailable:
        if len(unavailable) == 1:
            comment = f"Kernel module {unavailable[0]} is unavailable"
        else:
            comment = "Kernel modules {} are unavailable".format(", ".join(unavailable))
        _append_comment(ret, comment)
        ret["result"] = False

    # The remaining modules are not loaded and are available for loading
    available = list(set(not_loaded) - set(unavailable))
    loaded = {"yes": [], "no": [], "failed": []}
    loaded_by_dependency = []
    for mod in available:
        if mod in loaded_by_dependency:
            loaded["yes"].append(mod)
            continue
        load_result = __salt__["kmod.load"](mod, persist)
        if isinstance(load_result, (list, tuple)):
            if len(load_result) > 0:
                for module in load_result:
                    ret["changes"][module] = "loaded"
                    if module != mod:
                        loaded_by_dependency.append(module)
                loaded["yes"].append(mod)
            else:
                ret["result"] = False
                loaded["no"].append(mod)
        else:
            ret["result"] = False
            loaded["failed"].append([mod, load_result])

    # Update comment with results
    if len(loaded["yes"]) == 1:
        _append_comment(ret, "Loaded kernel module {}".format(loaded["yes"][0]))
    elif len(loaded["yes"]) > 1:
        _append_comment(
            ret, "Loaded kernel modules {}".format(", ".join(loaded["yes"]))
        )

    if len(loaded["no"]) == 1:
        _append_comment(ret, "Failed to load kernel module {}".format(loaded["no"][0]))
    if len(loaded["no"]) > 1:
        _append_comment(
            ret, "Failed to load kernel modules {}".format(", ".join(loaded["no"]))
        )

    if loaded["failed"]:
        for mod, msg in loaded["failed"]:
            _append_comment(ret, f"Failed to load kernel module {mod}: {msg}")

    return ret


def absent(name, persist=False, comment=True, mods=None):
    """
    Verify that the named kernel module is not loaded

    name
        The name of the kernel module to verify is not loaded

    persist
        Remove module from ``/etc/modules`` (or
        ``/etc/modules-load.d/salt_managed.conf`` if the ``systemd`` key is
        present in Grains.

    comment
        Comment out module in ``/etc/modules`` rather than remove it

    mods
        A list of modules to verify are unloaded.  If this argument is used,
        the ``name`` argument, although still required, is not used, and
        becomes a placeholder

        .. versionadded:: 2016.3.0
    """
    if not isinstance(mods, (list, tuple)):
        mods = [name]
    ret = {"name": name, "result": True, "changes": {}, "comment": ""}

    loaded_mods = __salt__["kmod.mod_list"]()
    if persist:
        persist_mods = __salt__["kmod.mod_list"](True)
        # Union of loaded modules and persistent modules
        loaded_mods = list(set(loaded_mods) | set(persist_mods))

    # Intersection of proposed modules and loaded modules
    to_unload = list(set(mods) & set(loaded_mods))
    if to_unload:
        if __opts__["test"]:
            ret["result"] = None
            if len(to_unload) == 1:
                _append_comment(
                    ret, f"Kernel module {to_unload[0]} is set to be removed"
                )
            elif len(to_unload) > 1:
                _append_comment(
                    ret,
                    "Kernel modules {} are set to be removed".format(
                        ", ".join(to_unload)
                    ),
                )
            return ret

        # Unload modules and collect results
        unloaded = {"yes": [], "no": [], "failed": []}
        for mod in to_unload:
            unload_result = __salt__["kmod.remove"](mod, persist, comment)
            if isinstance(unload_result, (list, tuple)):
                if len(unload_result) > 0:
                    for module in unload_result:
                        ret["changes"][module] = "removed"
                    unloaded["yes"].append(mod)
                else:
                    ret["result"] = False
                    unloaded["no"].append(mod)
            else:
                ret["result"] = False
                unloaded["failed"].append([mod, unload_result])

        # Update comment with results
        if len(unloaded["yes"]) == 1:
            _append_comment(ret, "Removed kernel module {}".format(unloaded["yes"][0]))
        elif len(unloaded["yes"]) > 1:
            _append_comment(
                ret, "Removed kernel modules {}".format(", ".join(unloaded["yes"]))
            )

        if len(unloaded["no"]) == 1:
            _append_comment(
                ret, "Failed to remove kernel module {}".format(unloaded["no"][0])
            )
        if len(unloaded["no"]) > 1:
            _append_comment(
                ret,
                "Failed to remove kernel modules {}".format(", ".join(unloaded["no"])),
            )

        if unloaded["failed"]:
            for mod, msg in unloaded["failed"]:
                _append_comment(ret, f"Failed to remove kernel module {mod}: {msg}")

        return ret

    else:
        if len(mods) == 1:
            ret["comment"] = f"Kernel module {mods[0]} is already removed"
        else:
            ret["comment"] = "Kernel modules {} are already removed".format(
                ", ".join(mods)
            )

        return ret
